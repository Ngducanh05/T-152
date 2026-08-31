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
  RewardCatalogItem,
  RewardSummary,
  ParkingVoucher,
  RewardTransaction,
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
  rewardCatalog: RewardCatalogItem[];
  vouchers: ParkingVoucher[];
  rewardLedger: RewardTransaction[];
  rewardLedgerAvailable: boolean;
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
  rewardCatalog: RewardCatalogItem[];
  vouchers: ParkingVoucher[];
  rewardLedger: RewardTransaction[];
  rewardLedgerAvailable: boolean;
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
  rewardCatalog: [],
  vouchers: [],
  rewardLedger: [],
  rewardLedgerAvailable: true,
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
  // Keep narrowly typed test doubles from older consumers compatible; the real
  // client always implements these methods and production failures still surface.
  const getCatalog = api.getRewardCatalog?.bind(api) ?? (async () => []);
  const getVouchers = api.getUserVouchers?.bind(api) ?? (async () => []);
  const getLedger = api.getRewardLedger?.bind(api);
  const [map, parkingSnapshot] = await Promise.all([
    api.getMap(signal),
    api.getParkingSnapshot(signal),
  ]);
  const { slots, status } = parkingSnapshot;
  if (!userId) {
    const [rewardConfiguration, rewardCatalog] = await Promise.all([api.getRewardConfiguration(signal), getCatalog(signal)]);
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
      rewardCatalog,
      vouchers: [],
      rewardLedger: [],
      rewardLedgerAvailable: true,
    };
  }
  const ledgerPromise = getLedger
    ? getLedger(userId, signal)
        .then((ledger) => ({ ledger, available: true }))
        .catch(() => ({ ledger: [], available: false }))
    : Promise.resolve({ ledger: [], available: true });
  const [userState, contributions, rewardCatalog, vouchers, ledgerResult] = await Promise.all([
    api.getUserParkingState(userId, signal),
    api.getUserContributions(userId, signal),
    getCatalog(signal),
    getVouchers(userId, signal),
    ledgerPromise,
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
    rewardCatalog,
    vouchers,
    rewardLedger: ledgerResult.ledger,
    rewardLedgerAvailable: ledgerResult.available,
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
