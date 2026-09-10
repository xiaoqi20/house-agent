import { useStore } from '../store';
import { getDemoStore } from '../data/demo';
import { comparisonMissingFields } from './calc';
import type { Contract, House } from '../types';

/** 普通候选房源（含历史演示数据，供只读快照使用） */
export const getHouse = (id: string | null): House | undefined =>
  (id ? useStore.getState().houses.find((h) => h.id === id) : undefined) ||
  (id ? getDemoStore().houses.find((h) => h.id === id) : undefined);

export const getContract = (id: string | null): Contract | undefined =>
  (id ? useStore.getState().contracts.find((c) => c.id === id) : undefined) ||
  (id ? getDemoStore().contracts.find((c) => c.id === id) : undefined);

/** 本次工作台中的候选房源（不含已放弃） */
export const activeHouses = (): House[] => useStore.getState().houses.filter((h) => h.status === 'active');

/** 是否属于本次工作台（历史演示数据只读） */
export const isLiveHouse = (id: string): boolean => useStore.getState().houses.some((h) => h.id === id);

/** 关键字段完整、可进入比较的候选房源（3—10 套） */
export const comparableHouses = (): House[] =>
  activeHouses().filter((h) => comparisonMissingFields(h, useStore.getState().prefs).length === 0);
