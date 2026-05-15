import axios from 'axios';
import { getTelegramInitData } from './telegram';
import type { Room, Receipt, PaymentSplit, RoomLiveState, ItemIntelligence, ItemCategory } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || API_BASE_URL.replace(/^http/, 'ws');

const toReceipt = (data: any): Receipt => ({
  id: String(data.id),
  paidAt: data.paidAt ?? data.paid_at ?? data.created_at ?? new Date().toISOString(),
  placeName: data.placeName ?? data.place_name ?? null,
  tip: Number(data.tip ?? 0),
  service: Number(data.service ?? 0),
  totalSum: Number(data.totalSum ?? data.total_sum ?? 0),
  items: (data.items ?? []).map((item: any) => ({
    id: String(item.id),
    name: item.name,
    price: Number(item.price ?? 0),
    quantity: Number(item.quantity ?? 1),
    assignedUsers: item.assignedUsers ?? item.assigned_users ?? [],
  })),
});

const toRoom = (data: any): Room => ({
  id: String(data.id),
  creatorId: String(data.creatorId ?? data.creator_id ?? '1'),
  createdAt: data.createdAt ?? data.created_at ?? new Date().toISOString(),
  isActive: Boolean(data.isActive ?? data.is_active ?? true),
  receiptId: data.receiptId ? String(data.receiptId) : data.receipt_id ? String(data.receipt_id) : null,
  receipt: data.receipt ? toReceipt(data.receipt) : undefined,
  participants: data.participants ?? [],
  shareCode: data.shareCode ?? data.public_key,
  shareLink: data.shareLink,
});

const makeRoomCode = () =>
  Math.random().toString(36).replace(/[^a-z0-9]/gi, '').slice(2, 8).toUpperCase().padEnd(6, 'X');

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add Telegram init data to all requests
api.interceptors.request.use((config) => {
  const initData = getTelegramInitData();
  if (initData) {
    config.headers['X-Telegram-Init-Data'] = initData;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string') {
      throw new Error(detail);
    }
    if (Array.isArray(detail) && detail[0]?.msg) {
      throw new Error(detail[0].msg);
    }
    if (error?.message) {
      throw new Error(error.message);
    }
    throw error;
  },
);

// Room API
export const roomAPI = {
  create: async (receiptId: string): Promise<Room> => {
    const publicKey = makeRoomCode();
    const { data } = await api.post('/rooms/', {
      name: 'Совместный чек',
      public_key: publicKey,
      creator_id: 1,
      receipt_id: Number(receiptId),
      status: 'active',
    });
    return toRoom(data);
  },

  getById: async (roomId: string): Promise<Room> => {
    const { data } = await api.get(`/rooms/${roomId}`);
    return data;
  },

  addParticipant: async (roomId: string, userId: string): Promise<Room> => {
    const { data } = await api.post(`/rooms/${roomId}/participants`, { userId });
    return data;
  },

  removeParticipant: async (roomId: string, userId: string): Promise<void> => {
    await api.delete(`/rooms/${roomId}/participants/${userId}`);
  },

  assignItemToUser: async (roomId: string, itemId: string, userId: string, quantity: number): Promise<Room> => {
    const { data } = await api.post(`/rooms/${roomId}/items/${itemId}/assign`, { userId, quantity });
    return data;
  },

  finalize: async (roomId: string): Promise<PaymentSplit[]> => {
    const { data } = await api.post(`/rooms/${roomId}/finalize`);
    return data;
  },

  delete: async (roomId: string): Promise<void> => {
    await api.delete(`/rooms/${roomId}`);
  },

  findByCode: async (code: string): Promise<Room> => {
    const { data } = await api.get(`/rooms/code/${code}`);
    return toRoom(data);
  },

  getState: async (roomId: string, participantId?: string | null): Promise<RoomLiveState> => {
    const { data } = await api.get(`/rooms/${roomId}/state`, {
      params: participantId ? { participantId } : undefined,
    });
    return data;
  },

  applyStateAction: async (roomId: string, action: Record<string, unknown>, actorParticipantId?: string | null): Promise<RoomLiveState> => {
    const { data } = await api.post(`/rooms/${roomId}/state/actions`, {
      ...action,
      ...(actorParticipantId ? { actorParticipantId } : {}),
      updatedAt: new Date().toISOString(),
    });
    return data;
  },

  upsertSplitParticipant: async (roomId: string, participantId: string, name: string, color: string): Promise<RoomLiveState> =>
    roomAPI.applyStateAction(roomId, { type: 'upsert_participant', participantId, name, color }),

  proposeSplit: async (
    roomId: string,
    proposalType: 'split_all_evenly' | 'split_item_evenly',
    fromParticipantId: string,
    participantIds: string[],
    itemId?: string,
  ): Promise<RoomLiveState> =>
    roomAPI.applyStateAction(roomId, { type: 'propose_split', proposalType, fromParticipantId, participantIds, itemId }),

  acceptProposal: async (roomId: string, proposalId: string, participantId: string): Promise<RoomLiveState> =>
    roomAPI.applyStateAction(roomId, { type: 'accept_proposal', proposalId, participantId }),

  declineProposal: async (roomId: string, proposalId: string, participantId: string): Promise<RoomLiveState> =>
    roomAPI.applyStateAction(roomId, { type: 'decline_proposal', proposalId, participantId }),

  proposeClaim: async (
    roomId: string,
    itemId: string,
    fromParticipantId: string,
    targetParticipantId: string,
    quantity?: number,
  ): Promise<RoomLiveState> =>
    roomAPI.applyStateAction(roomId, { type: 'propose_claim', itemId, fromParticipantId, targetParticipantId, quantity }),

  getItemIntelligence: async (roomId: string, participantId: string): Promise<ItemIntelligence[]> => {
    const { data } = await api.get(`/rooms/${roomId}/intelligence`, {
      params: { participantId },
    });
    return data.items ?? [];
  },

  rememberItemHistory: async (
    roomId: string,
    participantId: string,
    items: Array<{ name: string; quantity: number; category?: ItemCategory }>,
  ): Promise<void> => {
    await api.post(`/rooms/${roomId}/history`, { participantId, items });
  },
};

// Receipt API
export const receiptAPI = {
  create: async (file: File): Promise<Receipt> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/receipts/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return toReceipt(data);
  },

  getById: async (receiptId: string): Promise<Receipt> => {
    const { data } = await api.get(`/receipts/${receiptId}`);
    return data;
  },

  addItem: async (receiptId: string, name: string, price: number, quantity: number): Promise<Receipt> => {
    const { data } = await api.post(`/receipts/${receiptId}/items`, { name, price, quantity });
    return toReceipt(data);
  },

  updateItem: async (receiptId: string, itemId: string, name: string, price: number, quantity: number): Promise<Receipt> => {
    const { data } = await api.put(`/receipts/${receiptId}/items/${itemId}`, { name, price, quantity });
    return toReceipt(data);
  },

  removeItem: async (receiptId: string, itemId: string): Promise<Receipt> => {
    const { data } = await api.delete(`/receipts/${receiptId}/items/${itemId}`);
    return toReceipt(data);
  },

  updateTipAndService: async (receiptId: string, tip: number, service: number): Promise<Receipt> => {
    const { data } = await api.put(`/receipts/${receiptId}/tip-service`, { tip, service });
    return data;
  },
};

// User API
export const userAPI = {
  register: async (userId: string, username: string, firstName: string): Promise<{ id: string }> => {
    const { data } = await api.post('/users', { userId, username, firstName });
    return data;
  },

  getProfile: async (): Promise<{ id: string; username: string; firstName: string }> => {
    const { data } = await api.get('/users/me');
    return data;
  },
};

export default api;
