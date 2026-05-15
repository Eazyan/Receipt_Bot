import React, { useState } from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import { Button, Card, Pill } from '@/components/UI';
import type { ReceiptItem } from '@/types';
import type { ItemCategory } from '@/utils/itemIntelligence';
import { CATEGORY_LABELS, CATEGORY_TONES } from '@/utils/itemIntelligence';

const rub = (value: number) => `${value.toFixed(2)} ₽`;

export const getReceiptSubtotal = (items: ReceiptItem[]) =>
  items.reduce((sum, item) => sum + item.price * item.quantity, 0);

export const getSelectedSubtotal = (items: ReceiptItem[], selectedItems: Record<string, number>) =>
  items.reduce((sum, item) => sum + item.price * Math.min(selectedItems[item.id] || 0, item.quantity), 0);

const isProbablySuspicious = (item: ReceiptItem) => {
  const name = item.name.toLowerCase();
  return (
    item.price <= 0 ||
    name.includes('жайн') ||
    name.includes('жайка') ||
    name.includes('???') ||
    name.length < 4
  );
};

interface ReceiptItemListProps {
  items: ReceiptItem[];
  selectedItems?: Record<string, number>;
  onSelectItem?: (itemId: string, quantity: number) => void;
  mode?: 'view' | 'select' | 'edit';
  onEditItem?: (item: ReceiptItem) => void;
  onDeleteItem?: (itemId: string) => void;
  onSplitHalf?: (item: ReceiptItem) => void;
  onAssignAll?: (item: ReceiptItem) => void;
  onOfferToParticipant?: (item: ReceiptItem, participantId: string) => void;
  activeParticipantName?: string;
  claimButtonLabel?: string;
  splitButtonLabel?: string;
  getOfferTargets?: (item: ReceiptItem) => Array<{ id: string; name: string }>;
  getAllocationSummary?: (item: ReceiptItem) => Array<{ name: string; quantity: number; amount: number; isCurrent?: boolean }>;
  getCategory?: (item: ReceiptItem) => ItemCategory;
  getSuggestion?: (item: ReceiptItem) => string | null;
  onAcceptSuggestion?: (item: ReceiptItem) => void;
  getMaxSelectableQuantity?: (item: ReceiptItem) => number;
  getAllocatedQuantity?: (item: ReceiptItem) => number;
}

const IconButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }> = ({
  label,
  children,
  style,
  ...props
}) => (
  <button
    aria-label={label}
    title={label}
    style={{
      width: 38,
      height: 38,
      borderRadius: borderRadius.md,
      background: colors.surfaceAlt,
      color: colors.text,
      fontSize: 18,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      ...style,
    }}
    {...props}
  >
    {children}
  </button>
);

const QuantityStepper: React.FC<{
  quantity: number;
  selected: number;
  onSelect: (quantity: number) => void;
}> = ({ quantity, selected, onSelect }) => {
  const step = quantity % 1 === 0 ? 1 : 0.5;
  const nextValue = (value: number) => Math.max(0, Math.min(quantity, Number(value.toFixed(3))));
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '38px 1fr 38px', gap: spacing.sm, alignItems: 'center' }}>
      <IconButton label="Уменьшить" onClick={() => onSelect(nextValue(selected - step))}>−</IconButton>
      <div
        style={{
          minWidth: 46,
          height: 38,
          borderRadius: borderRadius.md,
          background: selected > 0 ? colors.secondaryBg : colors.surfaceAlt,
          color: selected > 0 ? colors.primary : colors.textSecondary,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 800,
          border: `1px solid ${selected > 0 ? 'rgba(47,128,237,0.22)' : colors.divider}`,
        }}
      >
        {Number.isInteger(selected) ? selected : selected.toFixed(2)}
      </div>
      <IconButton
        label="Увеличить"
        onClick={() => onSelect(nextValue(selected + step))}
        style={{ background: selected >= quantity ? colors.surfaceAlt : colors.primary, color: selected >= quantity ? colors.textSecondary : '#fff' }}
      >
        +
      </IconButton>
    </div>
  );
};

const ReceiptItemRow: React.FC<{
  item: ReceiptItem;
  selected?: number;
  onSelect?: (quantity: number) => void;
  mode?: 'view' | 'select' | 'edit';
  onEdit?: () => void;
  onDelete?: () => void;
  onSplitHalf?: () => void;
  onAssignAll?: () => void;
  onOfferToParticipant?: (participantId: string) => void;
  activeParticipantName?: string;
  claimButtonLabel?: string;
  splitButtonLabel?: string;
  offerTargets?: Array<{ id: string; name: string }>;
  allocationSummary?: Array<{ name: string; quantity: number; amount: number; isCurrent?: boolean }>;
  category?: ItemCategory;
  suggestion?: string | null;
  onAcceptSuggestion?: () => void;
  maxSelectableQuantity?: number;
  allocatedQuantity?: number;
}> = ({
  item,
  selected = 0,
  onSelect,
  mode = 'view',
  onEdit,
  onDelete,
  onSplitHalf,
  onAssignAll,
  onOfferToParticipant,
  activeParticipantName = 'Мне',
  claimButtonLabel = 'Забрать себе',
  splitButtonLabel = 'Предложить 50/50',
  offerTargets = [],
  allocationSummary = [],
  category,
  suggestion,
  onAcceptSuggestion,
  maxSelectableQuantity,
  allocatedQuantity = 0,
}) => {
  const lineTotal = item.price * item.quantity;
  const suspicious = isProbablySuspicious(item);
  const maxQuantity = Math.max(0, Math.min(item.quantity, maxSelectableQuantity ?? item.quantity));
  const allocationDone = allocatedQuantity >= item.quantity;
  const [dragStartX, setDragStartX] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState(0);
  const [actionsOpen, setActionsOpen] = useState(false);
  const canSwipe = mode === 'edit' && (onEdit || onDelete);

  const settleSwipe = (offset: number) => {
    if (!canSwipe) return;
    setActionsOpen(offset < -48);
    setDragOffset(0);
    setDragStartX(null);
  };

  return (
    <div
      style={{
        position: 'relative',
        overflow: 'hidden',
        backgroundColor: canSwipe ? colors.surfaceAlt : colors.surface,
        borderRadius: borderRadius.lg,
        border: `1px solid ${suspicious ? 'rgba(245,165,36,0.38)' : colors.divider}`,
        boxShadow: '0 1px 0 rgba(20,36,58,0.04)',
        animation: 'riseIn 0.22s ease both',
      }}
    >
      {canSwipe && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'stretch',
            background: colors.surfaceAlt,
          }}
        >
          {onEdit && (
            <button
              onClick={onEdit}
              style={{
                width: 82,
                background: colors.primary,
                color: '#fff',
                fontWeight: 850,
              }}
            >
              Править
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              style={{
                width: 82,
                background: colors.error,
                color: '#fff',
                fontWeight: 850,
              }}
            >
              Удалить
            </button>
          )}
        </div>
      )}
      <div
        onPointerDown={(event) => {
          if (!canSwipe) return;
          setDragStartX(event.clientX);
        }}
        onPointerMove={(event) => {
          if (!canSwipe || dragStartX == null) return;
          const nextOffset = Math.max(-164, Math.min(0, event.clientX - dragStartX + (actionsOpen ? -164 : 0)));
          setDragOffset(nextOffset);
        }}
        onPointerUp={() => settleSwipe(dragOffset)}
        onPointerCancel={() => settleSwipe(dragOffset)}
        style={{
          position: 'relative',
          zIndex: 1,
          backgroundColor: colors.surface,
          borderRadius: borderRadius.lg,
          padding: spacing.md,
          transform: canSwipe ? `translateX(${dragStartX == null ? (actionsOpen ? -164 : 0) : dragOffset}px)` : undefined,
          transition: dragStartX == null ? 'transform 0.18s ease' : 'none',
          touchAction: canSwipe ? 'pan-y' : undefined,
        }}
      >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md, alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ ...typography.body, fontWeight: 760, color: colors.text, wordBreak: 'break-word' }}>
            {item.name}
          </div>
          <div style={{ display: 'flex', gap: spacing.sm, flexWrap: 'wrap', marginTop: spacing.sm, alignItems: 'center' }}>
            <Pill tone={suspicious ? 'yellow' : 'blue'}>
              {item.quantity} × {rub(item.price)}
            </Pill>
            {mode === 'select' && allocatedQuantity > 0 && (
              <Pill tone={allocationDone ? 'green' : 'yellow'}>
                {allocationDone ? 'всё занято' : `занято ${Number.isInteger(allocatedQuantity) ? allocatedQuantity : allocatedQuantity.toFixed(2)}`}
              </Pill>
            )}
            {suspicious && <Pill tone="yellow">проверить</Pill>}
            {category && category !== 'other' && (
              <Pill tone={CATEGORY_TONES[category]}>{CATEGORY_LABELS[category]}</Pill>
            )}
          </div>
          {mode === 'select' && allocationSummary.length > 0 && (
            <div style={{ display: 'flex', gap: spacing.xs, flexWrap: 'wrap', marginTop: spacing.sm }}>
              {allocationSummary.map((allocation) => (
                <Pill key={allocation.name} tone={allocation.isCurrent ? 'blue' : 'green'}>
                  {allocation.name}: {rub(allocation.amount)}
                </Pill>
              ))}
            </div>
          )}
        </div>
        <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
          <div style={{ ...typography.subtitle, fontWeight: 850, color: colors.text }}>
            {rub(lineTotal)}
          </div>
          {selected > 0 && (
            <div style={{ ...typography.caption, color: colors.primary, fontWeight: 750, marginTop: 2 }}>
              {activeParticipantName}: {rub(item.price * selected)}
            </div>
          )}
        </div>
      </div>

      {mode === 'select' && onSelect && (
        <div style={{ marginTop: spacing.md, display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
          {suggestion && onAcceptSuggestion && (
            <button
              onClick={onAcceptSuggestion}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: spacing.sm,
                alignItems: 'center',
                padding: spacing.sm,
                borderRadius: borderRadius.md,
                background: colors.successSoft,
                color: colors.success,
                textAlign: 'left',
                fontWeight: 800,
              }}
            >
              <span>{suggestion}</span>
              <span>Забрать</span>
            </button>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm }}>
            <Button size="sm" variant={selected >= maxQuantity && maxQuantity > 0 ? 'primary' : 'secondary'} onClick={onAssignAll} disabled={maxQuantity <= 0 && selected <= 0}>
              {claimButtonLabel}
            </Button>
            <Button size="sm" variant={selected > 0 && selected < item.quantity ? 'primary' : 'secondary'} onClick={onSplitHalf} disabled={item.quantity <= 0}>
              {splitButtonLabel}
            </Button>
          </div>
          <QuantityStepper quantity={maxQuantity} selected={Math.min(selected, maxQuantity)} onSelect={onSelect} />
          {onOfferToParticipant && offerTargets.length > 0 && maxQuantity > 0 && (
            <div style={{ display: 'flex', gap: spacing.xs, flexWrap: 'wrap' }}>
              {offerTargets.map((target) => (
                <Button key={target.id} size="sm" variant="ghost" onClick={() => onOfferToParticipant(target.id)}>
                  → {target.name}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === 'edit' && (onEdit || onDelete) && (
        <div style={{ display: 'grid', gridTemplateColumns: onEdit && onDelete ? '1fr 96px' : '1fr', gap: spacing.sm, marginTop: spacing.md }}>
          {onEdit && (
            <Button fullWidth size="sm" variant="secondary" onClick={onEdit}>
              Править
            </Button>
          )}
          {onDelete && (
            <Button size="sm" variant="ghost" onClick={onDelete} style={{ color: colors.error }}>
              Удалить
            </Button>
          )}
        </div>
      )}
      </div>
    </div>
  );
};

export const ReceiptItemList: React.FC<ReceiptItemListProps> = ({
  items,
  selectedItems = {},
  onSelectItem,
  mode = 'view',
  onEditItem,
  onDeleteItem,
  onSplitHalf,
  onAssignAll,
  onOfferToParticipant,
  activeParticipantName,
  claimButtonLabel,
  splitButtonLabel,
  getOfferTargets,
  getAllocationSummary,
  getCategory,
  getSuggestion,
  onAcceptSuggestion,
  getMaxSelectableQuantity,
  getAllocatedQuantity,
}) => {
  if (items.length === 0) {
    return (
      <div
        style={{
          padding: spacing.lg,
          backgroundColor: colors.surface,
          borderRadius: borderRadius.lg,
          textAlign: 'center',
          color: colors.textSecondary,
          border: `1px dashed ${colors.border}`,
        }}
      >
        Позиций в чеке нет
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
      {items.map((item) => (
        <ReceiptItemRow
          key={item.id}
          item={item}
          selected={selectedItems[item.id] || 0}
          onSelect={(qty) => onSelectItem?.(item.id, qty)}
          mode={mode}
          onEdit={() => onEditItem?.(item)}
          onDelete={() => onDeleteItem?.(item.id)}
          onSplitHalf={() => onSplitHalf?.(item)}
          onAssignAll={() => onAssignAll?.(item)}
          onOfferToParticipant={(participantId) => onOfferToParticipant?.(item, participantId)}
          activeParticipantName={activeParticipantName}
          claimButtonLabel={claimButtonLabel}
          splitButtonLabel={splitButtonLabel}
          offerTargets={getOfferTargets?.(item)}
          allocationSummary={getAllocationSummary?.(item)}
          category={getCategory?.(item)}
          suggestion={getSuggestion?.(item)}
          onAcceptSuggestion={onAcceptSuggestion ? () => onAcceptSuggestion(item) : undefined}
          maxSelectableQuantity={getMaxSelectableQuantity?.(item)}
          allocatedQuantity={getAllocatedQuantity?.(item)}
        />
      ))}
    </div>
  );
};

interface ReceiptSummaryProps {
  items: ReceiptItem[];
  selectedItems?: Record<string, number>;
  tip?: number;
  service?: number;
  expectedTotal?: number;
}

export const ReceiptSummary: React.FC<ReceiptSummaryProps> = ({
  items,
  selectedItems = {},
  tip = 0,
  service = 0,
  expectedTotal,
}) => {
  const subtotal = getReceiptSubtotal(items);
  const total = subtotal + tip + service;
  const selectedTotal = getSelectedSubtotal(items, selectedItems);
  const hasSelection = Object.keys(selectedItems).length > 0;
  const difference = expectedTotal == null ? 0 : Math.abs(expectedTotal - subtotal);

  return (
    <Card elevated={difference > 0.02}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md }}>
        <div>
          <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750, textTransform: 'uppercase' }}>
            {hasSelection ? 'Выбрано вами' : 'Сверка чека'}
          </div>
          <div style={{ ...typography.heading, marginTop: 2 }}>
            {rub(hasSelection ? selectedTotal : total)}
          </div>
        </div>
        <Pill tone={difference <= 0.02 ? 'green' : 'yellow'}>
          {difference <= 0.02 ? 'сошлось' : `разница ${rub(difference)}`}
        </Pill>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: spacing.sm, marginTop: spacing.md }}>
        <div style={{ background: colors.background, borderRadius: borderRadius.md, padding: spacing.sm }}>
          <div style={{ ...typography.caption, color: colors.textSecondary }}>Позиции</div>
          <div style={{ ...typography.bodySmall, fontWeight: 800 }}>{items.length}</div>
        </div>
        <div style={{ background: colors.background, borderRadius: borderRadius.md, padding: spacing.sm }}>
          <div style={{ ...typography.caption, color: colors.textSecondary }}>Сумма строк</div>
          <div style={{ ...typography.bodySmall, fontWeight: 800 }}>{rub(subtotal)}</div>
        </div>
        <div style={{ background: colors.background, borderRadius: borderRadius.md, padding: spacing.sm }}>
          <div style={{ ...typography.caption, color: colors.textSecondary }}>Итог</div>
          <div style={{ ...typography.bodySmall, fontWeight: 800 }}>{rub(expectedTotal ?? total)}</div>
        </div>
      </div>
    </Card>
  );
};
