import { create } from 'zustand';
import type { ItemSplits, Room, Receipt, RoomLiveState, SplitParticipant, SplitProposal, SplitMode, TelegramUser, RoomRole, PaymentSplit } from '@/types';

const defaultSplitParticipants: SplitParticipant[] = [
  { id: 'local', name: 'Вы', color: '#2F80ED' },
];

interface AppState {
  // User
  telegramUser: TelegramUser | null;
  setTelegramUser: (user: TelegramUser) => void;

  // Navigation
  currentPage: string;
  setCurrentPage: (page: string) => void;

  // Room
  currentRoom: Room | null;
  currentRoomRole: RoomRole | null;
  setCurrentRoom: (room: Room, role: RoomRole) => void;
  clearCurrentRoom: () => void;

  // Receipt
  currentReceipt: Receipt | null;
  setCurrentReceipt: (receipt: Receipt) => void;
  clearCurrentReceipt: () => void;

  // Selection
  selectedItems: Record<string, number>; // itemId: quantity
  updateItemSelection: (itemId: string, quantity: number) => void;
  clearSelection: () => void;
  splitParticipants: SplitParticipant[];
  currentParticipantId: string | null;
  itemSplits: ItemSplits;
  liveProposals: SplitProposal[];
  liveSplitMode: SplitMode;
  liveCreatorParticipantId: string | null;
  setCurrentParticipant: (participantId: string) => void;
  applyLiveRoomState: (state: RoomLiveState) => void;

  // UI
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  error: string | null;
  setError: (error: string | null) => void;

  // Results
  paymentSplits: PaymentSplit[] | null;
  setPaymentSplits: (splits: PaymentSplit[]) => void;
  clearPaymentSplits: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // User
  telegramUser: null,
  setTelegramUser: (user) => set({ telegramUser: user }),

  // Navigation
  currentPage: 'home',
  setCurrentPage: (page) => set({ currentPage: page }),

  // Room
  currentRoom: null,
  currentRoomRole: null,
  setCurrentRoom: (room, role) => {
    const roomParticipants = room.participants?.map((participant, index) => ({
      id: participant.userId || `participant-${index}`,
      name: participant.firstName || participant.username || `Участник ${index + 1}`,
      color: ['#2F80ED', '#FFB020', '#19A974', '#8B5CF6', '#E5484D', '#00A3A3'][index % 6],
    })) || [];
    const splitParticipants = roomParticipants.length > 0 ? roomParticipants : defaultSplitParticipants;
    set({
      currentRoom: room,
      currentRoomRole: role,
      splitParticipants,
      currentParticipantId: null,
      selectedItems: {},
      itemSplits: {},
      liveProposals: [],
      liveSplitMode: 'items',
      liveCreatorParticipantId: room.creatorId,
      paymentSplits: null,
    });
  },
  clearCurrentRoom: () => set({ currentRoom: null, currentRoomRole: null, splitParticipants: defaultSplitParticipants, currentParticipantId: null, itemSplits: {}, liveProposals: [], liveSplitMode: 'items', liveCreatorParticipantId: null, selectedItems: {}, paymentSplits: null }),

  // Receipt
  currentReceipt: null,
  setCurrentReceipt: (receipt) => set({ currentReceipt: receipt }),
  clearCurrentReceipt: () => set({ currentReceipt: null }),

  // Selection
  selectedItems: {},
  updateItemSelection: (itemId, quantity) =>
    set((state) => {
      const newSelection = { ...state.selectedItems };
      if (quantity > 0) {
        newSelection[itemId] = quantity;
      } else {
        delete newSelection[itemId];
      }
      return { selectedItems: newSelection };
    }),
  clearSelection: () => set({ selectedItems: {}, itemSplits: {} }),
  splitParticipants: defaultSplitParticipants,
  currentParticipantId: null,
  itemSplits: {},
  liveProposals: [],
  liveSplitMode: 'items',
  liveCreatorParticipantId: null,
  setCurrentParticipant: (participantId) => set({ currentParticipantId: participantId }),
  applyLiveRoomState: (state) =>
    set((current) => {
      const currentParticipantId = current.currentParticipantId;
      return {
        splitParticipants: state.participants,
        itemSplits: state.itemSplits,
        liveProposals: state.proposals ?? [],
        liveSplitMode: state.splitMode ?? 'items',
        liveCreatorParticipantId: state.creatorParticipantId ?? null,
        currentParticipantId,
      };
    }),

  // UI
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),
  error: null,
  setError: (error) => set({ error }),

  // Results
  paymentSplits: null,
  setPaymentSplits: (splits) => set({ paymentSplits: splits }),
  clearPaymentSplits: () => set({ paymentSplits: null }),
}));
