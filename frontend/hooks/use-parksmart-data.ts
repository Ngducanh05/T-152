"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, parkSmartApi, type ParkSmartApiClient } from "@/lib/api";
import type {
  ActiveParkingSession,
  ContributionRecord,
  Location,
  ParkingMap,
  ParkingReservation,
  ParkingSlot,
  ParkingStatus,
  RewardConfiguration,
  RewardSummary,
} from "@/lib/types";

export const PARKING_POLL_INTERVAL_MS = 10_000;

export interface ParkSmartSnapshot {
  map: ParkingMap;
  status: ParkingStatus;
  slots: ParkingSlot[];
  currentLocation: Location | null;
  activeReservation: ParkingReservation | null;
  activeSession: ActiveParkingSession | null;
  rewardSummary: RewardSummary | null;
  rewardConfiguration: RewardConfiguration;
  contributions: ContributionRecord[];
}

export interface ParkSmartDataState {
  map: ParkingMap | null;
  status: ParkingStatus | null;
  slots: ParkingSlot[];
  currentLocation: Location | null;
  activeReservation: ParkingReservation | null;
  activeSession: ActiveParkingSession | null;
  rewardSummary: RewardSummary | null;
  rewardConfiguration: RewardConfiguration | null;
  contributions: ContributionRecord[];
  lastUpdatedAt: string | null;
  loading: boolean;
  refreshing: boolean;
  error: ApiError | null;
}

export interface ParkSmartData extends ParkSmartDataState {
  refresh: () => Promise<ParkSmartSnapshot>;
  applyCurrentLocation: (location: Location) => void;
}

const initialState: ParkSmartDataState = {
  map: null,
  status: null,
  slots: [],
  currentLocation: null,
  activeReservation: null,
  activeSession: null,
  rewardSummary: null,
  rewardConfiguration: null,
  contributions: [],
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
  const [map, parkingSnapshot] = await Promise.all([
    api.getMap(signal),
    api.getParkingSnapshot(signal),
  ]);
  const { slots, status } = parkingSnapshot;
  if (!userId) {
    const rewardConfiguration = await api.getRewardConfiguration(signal);
    return {
      map,
      slots,
      status,
      currentLocation: null,
      activeReservation: null,
      activeSession: null,
      rewardSummary: null,
      rewardConfiguration,
      contributions: [],
    };
  }
  const [userState, contributions] = await Promise.all([
    api.getUserParkingState(userId, signal),
    api.getUserContributions(userId, signal),
  ]);
  return {
    map,
    slots,
    status,
    currentLocation: userState.current_location,
    activeReservation: userState.active_reservation,
    activeSession: userState.active_session,
    rewardSummary: userState.reward_summary,
    rewardConfiguration: userState.reward_configuration,
    contributions,
  };
}

export function useParkSmartData(
  api: ParkSmartApiClient = parkSmartApi,
  userId: string | null = null,
): ParkSmartData {
  const [state, setState] = useState<ParkSmartDataState>(initialState);
  const mountedRef = useRef(false);
  const lifecycleControllerRef = useRef<AbortController | null>(null);
  const pollControllerRef = useRef<AbortController | null>(null);
  const refreshPromiseRef = useRef<Promise<ParkSmartSnapshot> | null>(null);

  const refresh = useCallback((): Promise<ParkSmartSnapshot> => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;
    pollControllerRef.current?.abort();
    setState((current) => ({ ...current, refreshing: true }));
    const signal = lifecycleControllerRef.current?.signal;
    const promise = loadAuthoritativeState(api, userId, signal)
      .then((snapshot) => {
        if (mountedRef.current) {
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
        if (mountedRef.current && !signal?.aborted) {
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
        refreshPromiseRef.current = null;
      });
    refreshPromiseRef.current = promise;
    return promise;
  }, [api, userId]);

  useEffect(() => {
    mountedRef.current = true;
    lifecycleControllerRef.current = new AbortController();

    async function loadInitialState() {
      const existingRefresh = refreshPromiseRef.current;
      if (existingRefresh) {
        try {
          await existingRefresh;
        } catch {
          // React Strict Mode intentionally mounts, cleans up, and mounts again
          // in development. The first lifecycle's aborted request must settle
          // before the active lifecycle can start its own authoritative load.
        }
      }
      if (mountedRef.current && !refreshPromiseRef.current) {
        await refresh();
      }
    }

    void loadInitialState().catch(() => undefined);

    async function pollParking() {
      if (refreshPromiseRef.current || pollControllerRef.current) return;
      const controller = new AbortController();
      pollControllerRef.current = controller;
      try {
        const snapshot = await api.getParkingSnapshot(controller.signal);
        if (mountedRef.current) {
          setState((current) => ({
            ...current,
            slots: snapshot.slots,
            status: snapshot.status,
            lastUpdatedAt: new Date().toISOString(),
            error: null,
          }));
        }
      } catch (error) {
        if (mountedRef.current && !controller.signal.aborted) {
          setState((current) => ({
            ...current,
            error: asApiError(error, "Unable to refresh parking data."),
          }));
        }
      } finally {
        if (pollControllerRef.current === controller) {
          pollControllerRef.current = null;
        }
      }
    }

    const timer = window.setInterval(
      () => void pollParking(),
      PARKING_POLL_INTERVAL_MS,
    );

    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
      pollControllerRef.current?.abort();
      lifecycleControllerRef.current?.abort();
      pollControllerRef.current = null;
      lifecycleControllerRef.current = null;
    };
  }, [api, refresh, userId]);

  const applyCurrentLocation = useCallback((location: Location) => {
    setState((current) => ({
      ...current,
      currentLocation: location,
      lastUpdatedAt: new Date().toISOString(),
      error: null,
    }));
  }, []);

  return { ...state, refresh, applyCurrentLocation };
}
