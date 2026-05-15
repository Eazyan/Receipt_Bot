import type { ReceiptItem, SplitParticipant, ItemCategory } from '@/types';

export type { ItemCategory };

export const CATEGORY_LABELS: Record<ItemCategory, string> = {
  food: 'еда',
  drink: 'напиток',
  alcohol: 'алкоголь',
  delivery: 'доставка',
  packaging: 'упаковка',
  discount: 'скидка',
  other: 'прочее',
};

export const CATEGORY_TONES: Record<ItemCategory, 'blue' | 'green' | 'yellow' | 'red' | 'dark'> = {
  food: 'green',
  drink: 'blue',
  alcohol: 'yellow',
  delivery: 'dark',
  packaging: 'yellow',
  discount: 'red',
  other: 'blue',
};

const normalizeName = (value: string) =>
  value
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^a-zа-я0-9 ]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export type ParsedCommand =
  | { type: 'claim_self'; item: ReceiptItem }
  | { type: 'offer_to'; item: ReceiptItem; participant: SplitParticipant }
  | { type: 'split_item'; item: ReceiptItem }
  | { type: 'split_all' };

export const parseSplitCommand = (
  command: string,
  items: ReceiptItem[],
  participants: SplitParticipant[],
  currentParticipantId: string,
): ParsedCommand | null => {
  const text = normalizeName(command);
  if (!text) return null;
  if ((text.includes('поровну') || text.includes('пополам') || text.includes('50 50')) && (text.includes('чек') || text.includes('все'))) {
    return { type: 'split_all' };
  }

  const item = items.find((candidate) => {
    const name = normalizeName(candidate.name);
    return name.split(' ').some((token) => token.length >= 4 && text.includes(token)) || text.includes(name);
  });
  if (!item) return null;

  if (text.includes('пополам') || text.includes('50 50')) {
    return { type: 'split_item', item };
  }
  if (text.includes('мне') || text.includes('себе') || text.includes('мой') || text.includes('мое')) {
    return { type: 'claim_self', item };
  }

  const target = participants.find((participant) => {
    if (participant.id === currentParticipantId) return false;
    const name = normalizeName(participant.name);
    return name.length >= 2 && text.includes(name);
  });
  if (target) {
    return { type: 'offer_to', item, participant: target };
  }

  return null;
};
