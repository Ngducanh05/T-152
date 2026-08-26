"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, parkSmartApi, type ParkSmartApiClient } from "@/lib/api";
import type {
  ActiveParkingSession,
  Location,
  ParkingMap,
  ParkingReservation,
  ParkingSlot,
  ParkingStatus,
} from "@/lib/types";

export const PARKING_POLL_INTERVAL_MS = 10_000;

export interface ParkSmartSnapshot {
  map: ParkingMap;
  status: ParkingStatus;
  slots: ParkingSlot[];
  currentLocation: Location | null;
  activeReservation: ParkingReservation | null;
  activeSession: ActiveParkingSession | null;
}

export interface ParkSmartDataState {
  map: ParkingMap | null;
  status: ParkingStatus | null;
  slots: ParkingSlot[];
  currentLocation: Location | null;
  activeReservation: ParkingReservation | null;
  activeSession: ActiveParkingSession | null;
  lastUpdatedAt: string | null;
  loading: boolean;
  refreshing: boolean;
  error: ApiError | null;
}

export interface ParkSmartData extends ParkSmartDataState {
  refresh: () => Promise<ParkSmartSnapshot>;
}

const initialState: ParkSmartDataState = {
  map: null,
  status: null,
  slots: [],
  currentLocation: null,
  activeReservation: null,
  activeSession: null,
  lastUpdatedAt: null,
  loading: true,
  refreshing: false,
  error: null,
};

function asApiError(error: unknown, message: string) {
  return error instanceof ApiError
    ? error
    : new ApiError({ code: "NETWORK_ERROR", message, status: 0 });
}

export async function loadAuthoritativeState(
  api: ParkSmartApiClient,
  userId: string | null,
  signal?: AbortSignal,
): Promise<ParkSmartSnapshot> {
  const [map, slots, status] =
    await Promise.all([
      api.getMap(signal),
      api.getSlots({}, signal),
      api.getParkingStatus(signal),
    ]);

  if (!userId) {
    return {
      map,
      slots,
      status,
      currentLocation: null,
      activeReservation: null,
      activeSession: null,
    };
  }

  const [currentLocation, activeReservation, activeSession] =
    await Promise.all([
      api.getCurrentLocation(userId, signal),
      api.getActiveReservation(userId, signal),
      api.getActiveSession(userId, signal),
    ]);

  return { map, slots, status, currentLocation, activeReservation, activeSession };
}

export function useParkSmartData(
  api: ParkSmartApiClient = parkSmartApi,
  userId: string | null = null,
): ParkSmartData {
  const [state, setState] = useState<ParkSmartDataState>(initialState);
  const mountedRef = useRef(false);
  const lifecycleControllerRef = useRef<AbortController | null>(null);
  const pollControllerRef = useRef<AbortController | null>(null);
  const refreshPromiseRef = useRef<{
    controller: AbortController | null;
    promise: Promise<ParkSmartSnapshot>;
  } | null>(null);

  const refresh = useCallback((): Promise<ParkSmartSnapshot> => {
    const controller = lifecycleControllerRef.current;
    const existingRefresh = refreshPromiseRef.current;
    if (existingRefresh?.controller === controller) {
      return existingRefresh.promise;
    }

    pollControllerRef.current?.abort();
    setState((current) => ({ ...current, refreshing: true }));
    const signal = controller?.signal;
    const promise = loadAuthoritativeState(api, userId, signal)
      .then((snapshot) => {
        if (
          mountedRef.current &&
          lifecycleControllerRef.current === controller
        ) {
          setState({
            ...snapshot,
            lastUpdatedAt: new Date().toISOString(),
            loading: false,
            refreshing: false,
            error: null,
          });
        }
        return snapshot;
      })
      .catch((error: unknown) => {
        if (
          mountedRef.current &&
          lifecycleControllerRef.current === controller &&
          !signal?.aborted
        ) {
          setState((current) => ({
            ...current,
            loading: false,
            refreshing: false,
            error: asApiError(error, "Unable to refresh ParkSmart data."),
          }));
        }
        throw error;
      })
      .finally(() => {
        if (refreshPromiseRef.current?.promise === promise) {
          refreshPromiseRef.current = null;
        }
      });
    refreshPromiseRef.current = { controller, promise };
    return promise;
  }, [api, userId]);

  useEffect(() => {
    mountedRef.current = true;
    const lifecycleController = new AbortController();
    lifecycleControllerRef.current = lifecycleController;
    let active = true;
    let timer: number | null = null;

    setState((current) => ({
      ...current,
      currentLocation: null,
      activeReservation: null,
      activeSession: null,
      loading: true,
      error: null,
    }));

    async function loadInitialState() {
      const existingRefresh = refreshPromiseRef.current;
      if (existingRefresh) {
        try {
          await existingRefresh.promise;
        } catch {
          // React Strict Mode intentionally mounts, cleans up, and mounts again
          // in development. The first lifecycle's aborted request must settle
          // before the active lifecycle can start its own authoritative load.
        }
      }
      if (
        active &&
        mountedRef.current &&
        lifecycleControllerRef.current === lifecycleController &&
        !refreshPromiseRef.current
      ) {
        await refresh();
      }
    }

    async function pollParking() {
      if (!active || lifecycleController.signal.aborted) return;
      if (refreshPromiseRef.current || pollControllerRef.current) {
        timer = window.setTimeout(pollParking, PARKING_POLL_INTERVAL_MS);
        return;
      }

      const controller = new AbortController();
      pollControllerRef.current = controller;
      try {
        const [slots, status] = await Promise.all([
          api.getSlots({}, controller.signal),
          api.getParkingStatus(controller.signal),
        ]);
        if (
          active &&
          mountedRef.current &&
          lifecycleControllerRef.current === lifecycleController
        ) {
          setState((current) => ({
            ...current,
            slots,
            status,
            lastUpdatedAt: new Date().toISOString(),
            error: null,
          }));
        }
      } catch (error) {
        if (
          active &&
          mountedRef.current &&
          lifecycleControllerRef.current === lifecycleController &&
          !controller.signal.aborted
        ) {
          setState((current) => ({
            ...current,
            error: asApiError(error, "Unable to refresh parking data."),
          }));
        }
      } finally {
        if (pollControllerRef.current === controller) {
          pollControllerRef.current = null;
        }
        if (active && !lifecycleController.signal.aborted) {
          timer = window.setTimeout(pollParking, PARKING_POLL_INTERVAL_MS);
        }
      }
    }

    void loadInitialState()
      .catch(() => undefined)
      .finally(() => {
        if (active && !lifecycleController.signal.aborted) {
          timer = window.setTimeout(pollParking, PARKING_POLL_INTERVAL_MS);
        }
      });

    return () => {
      active = false;
      mountedRef.current = false;
      if (timer) window.clearTimeout(timer);
      if (pollControllerRef.current) {
        pollControllerRef.current.abort();
        pollControllerRef.current = null;
      }
      lifecycleController.abort();
      if (lifecycleControllerRef.current === lifecycleController) {
        lifecycleControllerRef.current = null;
      }
    };
  }, [api, refresh]);

  return { ...state, refresh };
}
