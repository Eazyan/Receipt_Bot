// Telegram Mini App User
export interface TelegramUser {
  id: number;
  is_bot: boolean;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

// Room related types
export interface RoomParticipant {
  userId: string;
  username: string;
  firstName: string;
  selected: Record<string, number>; // item_id: quantity_selected
}

export interface SplitParticipant {
  id: string;
  name: string;
  color: string;
}

export type ItemSplits = Record<string, Record<string, number>>;
export type SplitMode = 'even' | 'items' | 'mixed';
export type ItemCategory = 'food' | 'drink' | 'alcohol' | 'delivery' | 'packaging' | 'discount' | 'other';

export interface SplitProposal {
  id: string;
  type: 'split_all_evenly' | 'split_item_evenly' | 'claim_item';
  itemId?: string;
  fromParticipantId: string;
  targetParticipantId?: string;
  participantIds: string[];
  acceptedBy: string[];
  declinedBy: string[];
  status: 'open' | 'accepted' | 'declined';
  createdAt: string | null;
}

export interface RoomLiveState {
  roomId: string;
  version: number;
  participants: SplitParticipant[];
  creatorParticipantId: string;
  splitMode: SplitMode;
  items: Array<{
    id: string;
    name: string;
    price: number;
    quantity: number;
  }>;
  itemSplits: ItemSplits;
  proposals: SplitProposal[];
  updatedAt: string | null;
}

export interface ItemIntelligence {
  id: string;
  category: ItemCategory;
  category_confidence: number;
  suggest_for_participant: boolean;
  suggestion_confidence: number;
  matched_history_item: string | null;
}

export interface ReceiptItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
  assignedUsers: string[];
}

export interface Receipt {
  id: string;
  paidAt: string;
  placeName?: string | null;
  tip: number;
  service: number;
  items: ReceiptItem[];
  totalSum: number;
}

export interface Room {
  id: string;
  creatorId: string;
  createdAt: string;
  isActive: boolean;
  receiptId: string | null;
  receipt?: Receipt;
  participants: RoomParticipant[];
  shareLink?: string;
  shareCode?: string;
}

export type RoomRole = 'creator' | 'participant';

// Payment calculation
export interface PaymentSplit {
  userId: string;
  username: string;
  items: Array<{
    name: string;
    quantity: number;
    price: number;
    subtotal: number;
  }>;
  subtotal: number;
  taxShare: number;
  tipShare: number;
  total: number;
}

// UI State
export type AppPage = 'home' | 'create-room' | 'room' | 'select-items' | 'results' | 'room-code';
