import { create } from "zustand";
import type { PermissionRequest } from "../lib/schemas";

export interface InputRequest {
  prompt: string;
  input_type: "text" | "password";
}

interface PermissionState {
  pendingRequest: PermissionRequest | null;
  setPendingRequest: (req: PermissionRequest | null) => void;
  pendingInputRequest: InputRequest | null;
  setPendingInputRequest: (req: InputRequest | null) => void;
}

export const usePermissionStore = create<PermissionState>((set) => ({
  pendingRequest: null,
  setPendingRequest: (pendingRequest) => set({ pendingRequest }),
  pendingInputRequest: null,
  setPendingInputRequest: (pendingInputRequest) => set({ pendingInputRequest }),
}));
