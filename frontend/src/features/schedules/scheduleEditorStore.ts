import { create } from "zustand";
import type { ScheduleOperation } from "../../api/client";

export interface EditorHistoryEntry {
  forward: ScheduleOperation[];
  inverse: ScheduleOperation[];
}

interface ScheduleEditorState {
  viewMode: "overview" | "wave";
  selectedWaveNo: number;
  undoStack: EditorHistoryEntry[];
  redoStack: EditorHistoryEntry[];
  setViewMode: (mode: "overview" | "wave") => void;
  setSelectedWaveNo: (waveNo: number) => void;
  record: (entry: EditorHistoryEntry) => void;
  commitUndo: () => void;
  commitRedo: (inverse: ScheduleOperation[]) => void;
  reset: () => void;
}

export const useScheduleEditorStore = create<ScheduleEditorState>((set) => ({
  viewMode: "overview",
  selectedWaveNo: 1,
  undoStack: [],
  redoStack: [],
  setViewMode: (viewMode) => set({ viewMode }),
  setSelectedWaveNo: (selectedWaveNo) => set({ selectedWaveNo }),
  record: (entry) =>
    set((state) => ({ undoStack: [...state.undoStack, entry], redoStack: [] })),
  commitUndo: () =>
    set((state) => {
      const entry = state.undoStack.at(-1);
      if (!entry) return state;
      return {
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, entry],
      };
    }),
  commitRedo: (inverse) =>
    set((state) => {
      const entry = state.redoStack.at(-1);
      if (!entry) return state;
      return {
        redoStack: state.redoStack.slice(0, -1),
        undoStack: [...state.undoStack, { ...entry, inverse }],
      };
    }),
  reset: () =>
    set({ viewMode: "overview", selectedWaveNo: 1, undoStack: [], redoStack: [] }),
}));
