"use client";

import { useEffect, useState } from "react";

import { ApiError, parkSmartApi, type ParkSmartApiClient } from "@/lib/api";
import type {
  ActiveParkingSession,
  Location,
  ParkingMap,
  ParkingReservation,
  ParkingSlot,
  ParkingStatus,
} from "@/lib/types";

export const DEMO_USER_ID = "USER-001";
export const PARKING_POLL_INTERVAL_MS = 2_000;

export interface ParkSmartDataState {
  map: ParkingMap | null;
  status: ParkingStatus | null;
  slots: ParkingSlot[];
  currentLocation: Location | null;
  activeReservation: ParkingReservation | null;
  activeSession: ActiveParkingSession | null;
  loading: boolean;
  error: ApiError | null;
}

const initialState: ParkSmartDataState = {
  map: null,
  status: null,
  slots: [],
  currentLocation: null,
  activeReservation: null,
  activeSession: null,
  loading: true,
  error: null,
};

export function useParkSmartData(
  api: ParkSmartApiClient = parkSmartApi,
  userId = DEMO_USER_ID,
): ParkSmartDataState {
  const [state, setState] = useState<ParkSmartDataState>(initialState);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let initialLoadFinished = false;
    let pollInFlight = false;

    async function loadInitial() {
      try {
        const [map, status, currentLocation, activeReservation, activeSession] =
          await Promise.all([
            api.getMap(controller.signal),
            api.getParkingStatus(controller.signal),
            api.getCurrentLocation(userId, controller.signal),
            api.getActiveReservation(userId, controller.signal),
            api.getActiveSession(userId, controller.signal),
          ]);
        if (disposed) return;
        setState({
          map,
          status,
          slots: map.slots,
          currentLocation,
          activeReservation,
          activeSession,
          loading: false,
          error: null,
        });
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        setState((current) => ({
          ...current,
          loading: false,
          error:
            error instanceof ApiError
              ? error
              : new ApiError({
                  code: "NETWORK_ERROR",
                  message: "Unable to load ParkSmart data.",
                  status: 0,
                }),
        }));
      } finally {
        initialLoadFinished = true;
      }
    }

    async function pollParking() {
      if (disposed || !initialLoadFinished || pollInFlight) return;
      pollInFlight = true;
      try {
        const [slots, status] = await Promise.all([
          api.getSlots({}, controller.signal),
          api.getParkingStatus(controller.signal),
        ]);
        if (!disposed) {
          setState((current) => ({ ...current, slots, status, error: null }));
        }
      } catch (error) {
        if (!disposed && !controller.signal.aborted) {
          setState((current) => ({
            ...current,
            error:
              error instanceof ApiError
                ? error
                : new ApiError({
                    code: "NETWORK_ERROR",
                    message: "Unable to refresh parking data.",
                    status: 0,
                  }),
          }));
        }
      } finally {
        pollInFlight = false;
      }
    }

    void loadInitial();
    const timer = window.setInterval(
      () => void pollParking(),
      PARKING_POLL_INTERVAL_MS,
    );

    return () => {
      disposed = true;
      window.clearInterval(timer);
      controller.abort();
    };
  }, [api, userId]);

  return state;
}
