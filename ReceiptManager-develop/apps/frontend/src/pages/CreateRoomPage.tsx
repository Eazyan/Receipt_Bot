import React, { useEffect, useMemo, useRef, useState } from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import {
  PageContainer,
  PageContent,
  PageFooter,
  Button,
  Input,
  Header,
  Card,
  ErrorAlert,
  Loading,
  Pill,
  BottomSheet,
} from '@/components/UI';
import { ReceiptItemList, ReceiptSummary, getReceiptSubtotal } from '@/components/ReceiptItems';
import { useAppStore } from '@/hooks/useAppStore';
import { receiptAPI, roomAPI } from '@/utils/api';
import { hapticFeedback, shareText, showTelegramAlert } from '@/utils/telegram';
import type { Receipt, ReceiptItem } from '@/types';

type CreateRoomStep = 'upload' | 'review' | 'share';
type ToastState = {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
};

const rub = (value: number) => `${value.toFixed(2)} ₽`;

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Дата не распознана';
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
};

const isSuspiciousName = (name: string) => {
  const lower = name.toLowerCase();
  return lower.includes('жайка') || lower.includes('???') || lower.length < 4;
};

export const CreateRoomPage: React.FC = () => {
  const { setCurrentPage, setCurrentRoom, setCurrentParticipant, applyLiveRoomState, telegramUser } = useAppStore();
  const [step, setStep] = useState<CreateRoomStep>('upload');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState<string | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');
  const [newItemQty, setNewItemQty] = useState('1');
  const [editingItem, setEditingItem] = useState<ReceiptItem | null>(null);
  const [editItemName, setEditItemName] = useState('');
  const [editItemPrice, setEditItemPrice] = useState('');
  const [editItemQty, setEditItemQty] = useState('1');
  const [shareCode, setShareCode] = useState('');
  const [creatorName, setCreatorName] = useState(() => {
    const saved = window.localStorage.getItem('receipt-manager-name');
    return saved || telegramUser?.first_name || '';
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toastTimerRef = useRef<number | null>(null);

  const receiptSubtotal = receipt ? getReceiptSubtotal(receipt.items) : 0;
  const totalDelta = receipt ? Math.abs(receipt.totalSum - receiptSubtotal) : 0;
  const suspiciousCount = useMemo(
    () => receipt?.items.filter((item) => item.price <= 0 || isSuspiciousName(item.name)).length ?? 0,
    [receipt],
  );

  useEffect(() => () => {
    if (receiptPreviewUrl) {
      URL.revokeObjectURL(receiptPreviewUrl);
    }
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
  }, [receiptPreviewUrl]);

  const flashToast = (message: string, action?: { label: string; onAction: () => void }, duration = 2400) => {
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast({ message, actionLabel: action?.label, onAction: action?.onAction });
    toastTimerRef.current = window.setTimeout(() => setToast(null), duration);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    setError(null);
    setToast(null);
    setIsPreviewOpen(false);
    setReceiptPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return URL.createObjectURL(file);
    });

    try {
      const parsedReceipt = await receiptAPI.create(file);
      setReceipt(parsedReceipt);
      setStep('review');
      hapticFeedback('success');
      flashToast('Чек распознан. Проверьте строки перед разделением.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось распознать чек';
      setError(message);
      hapticFeedback('impact');
      showTelegramAlert(message);
    } finally {
      setIsLoading(false);
      e.target.value = '';
    }
  };

  const handleAddItem = async () => {
    if (!receipt || !newItemName.trim() || !newItemPrice.trim()) {
      setError('Заполните название и цену');
      return;
    }

    const price = Number(newItemPrice);
    const quantity = Number(newItemQty);
    if (!Number.isFinite(price) || price < 0 || !Number.isFinite(quantity) || quantity <= 0) {
      setError('Проверьте цену и количество');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const updated = await receiptAPI.addItem(receipt.id, newItemName.trim(), price, quantity);
      setReceipt(updated);
      setNewItemName('');
      setNewItemPrice('');
      setNewItemQty('1');
      hapticFeedback('success');
      flashToast('Позиция добавлена');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка при добавлении позиции';
      setError(message);
      hapticFeedback('impact');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!receipt) return;
    const itemToDelete = receipt.items.find((item) => item.id === itemId);
    if (!itemToDelete) return;

    setIsLoading(true);
    setError(null);

    try {
      const updated = await receiptAPI.removeItem(receipt.id, itemId);
      setReceipt(updated);
      hapticFeedback('success');
      flashToast('Позиция удалена', { label: 'Вернуть', onAction: () => handleUndoDelete(itemToDelete) }, 5200);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка при удалении позиции';
      setError(message);
      hapticFeedback('impact');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUndoDelete = async (item: ReceiptItem) => {
    if (!receipt) return;
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    setIsLoading(true);
    setError(null);
    setToast(null);

    try {
      const updated = await receiptAPI.addItem(receipt.id, item.name, item.price, item.quantity);
      setReceipt(updated);
      hapticFeedback('success');
      flashToast('Позиция восстановлена');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось вернуть позицию';
      setError(message);
      hapticFeedback('impact');
    } finally {
      setIsLoading(false);
    }
  };

  const renderToast = () => toast && (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: toast.onAction ? '1fr auto' : '1fr',
        gap: spacing.sm,
        alignItems: 'center',
        padding: `${spacing.sm}px ${spacing.md}px`,
        borderRadius: 999,
        background: colors.text,
        color: '#fff',
        boxShadow: `0 12px 28px ${colors.shadow}`,
        animation: 'riseIn 0.18s ease both',
      }}
    >
      <span style={{ ...typography.bodySmall, fontWeight: 750 }}>{toast.message}</span>
      {toast.onAction && (
        <button
          onClick={toast.onAction}
          style={{
            background: 'rgba(255,255,255,0.14)',
            color: '#fff',
            borderRadius: 999,
            padding: '7px 10px',
            fontWeight: 850,
          }}
        >
          {toast.actionLabel}
        </button>
      )}
    </div>
  );

  const startEditItem = (item: ReceiptItem) => {
    setEditingItem(item);
    setEditItemName(item.name);
    setEditItemPrice(String(item.price));
    setEditItemQty(String(item.quantity));
    setError(null);
  };

  const cancelEditItem = () => {
    setEditingItem(null);
    setEditItemName('');
    setEditItemPrice('');
    setEditItemQty('1');
  };

  const handleSaveEditedItem = async () => {
    if (!receipt || !editingItem || !editItemName.trim() || !editItemPrice.trim()) {
      setError('Заполните название и цену');
      return;
    }

    const price = Number(editItemPrice);
    const quantity = Number(editItemQty);
    if (!Number.isFinite(price) || price < 0 || !Number.isFinite(quantity) || quantity <= 0) {
      setError('Проверьте цену и количество');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const updated = await receiptAPI.updateItem(receipt.id, editingItem.id, editItemName.trim(), price, quantity);
      setReceipt(updated);
      cancelEditItem();
      hapticFeedback('success');
      flashToast('Позиция обновлена');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка при редактировании позиции';
      setError(message);
      hapticFeedback('impact');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateRoom = async () => {
    if (!receipt) return;
    if (!creatorName.trim()) {
      setError('Введите ваше имя для комнаты');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const room = await roomAPI.create(receipt.id);
      const code = room.shareCode || room.id.slice(0, 6).toUpperCase();
      window.localStorage.setItem('receipt-manager-name', creatorName.trim());
      const state = await roomAPI.upsertSplitParticipant(room.id, room.creatorId, creatorName.trim(), '#2F80ED');
      setCurrentRoom({ ...room, receipt }, 'creator');
      applyLiveRoomState(state);
      setCurrentParticipant(room.creatorId);
      setShareCode(code);
      setStep('share');
      hapticFeedback('success');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка при создании комнаты';
      setError(message);
      hapticFeedback('impact');
      showTelegramAlert(message);
    } finally {
      setIsLoading(false);
    }
  };

  const copyCode = async () => {
    if (!shareCode) return;
    try {
      await navigator.clipboard.writeText(shareCode);
      hapticFeedback('success');
      flashToast('Код скопирован');
    } catch {
      showTelegramAlert(shareCode);
    }
  };

  const shareRoom = async () => {
    if (!shareCode) return;
    const text = [
      'Заходи разделить чек',
      `Код комнаты: ${shareCode}`,
      receipt ? `Итого: ${rub(receipt.totalSum)} · ${receipt.items.length} поз.` : '',
    ].filter(Boolean).join('\n');
    const ok = await shareText(text, 'Разделить чек');
    if (ok) {
      hapticFeedback('success');
      flashToast('Можно отправлять код в Telegram');
    } else {
      showTelegramAlert(text);
    }
  };

  if (step === 'upload') {
    return (
      <PageContainer>
        <Header title="Новый чек" subtitle="Фото, OCR и комната для друга" onBack={() => setCurrentPage('home')} />

        <PageContent>
          {isLoading && <Loading fullScreen label="AI читает чек..." />}
          {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

          <div
            style={{
              background: `linear-gradient(145deg, ${colors.surface}, ${colors.secondaryBg})`,
              borderRadius: 28,
              padding: 22,
              minHeight: 340,
              border: `1px solid ${colors.divider}`,
              position: 'relative',
              overflow: 'hidden',
              boxShadow: `0 20px 46px ${colors.shadow}`,
            }}
          >
            <div
              style={{
                width: 188,
                height: 232,
                margin: '8px auto 0',
                borderRadius: 18,
                background: '#fff',
                boxShadow: '0 16px 34px rgba(20,36,58,0.14)',
                padding: 18,
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: 0,
                  height: 36,
                  background: 'linear-gradient(180deg, rgba(47,128,237,0.16), rgba(47,128,237,0))',
                  animation: 'scanLine 2.1s ease-in-out infinite',
                }}
              />
              <div style={{ height: 8, width: 80, borderRadius: 99, background: colors.border, marginBottom: 18 }} />
              {[0, 1, 2, 3, 4, 5].map((idx) => (
                <div key={idx} style={{ display: 'flex', gap: 8, marginBottom: 13 }}>
                  <div style={{ height: 8, flex: 1, borderRadius: 999, background: idx === 2 ? colors.warningSoft : colors.surfaceAlt }} />
                  <div style={{ height: 8, width: 42, borderRadius: 999, background: idx === 4 ? colors.successSoft : colors.border }} />
                </div>
              ))}
              <div style={{ height: 1, background: colors.divider, margin: '18px 0 12px' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 900 }}>
                <span>ИТОГ</span>
                <span>...</span>
              </div>
            </div>
            <div style={{ textAlign: 'center', marginTop: spacing.xl }}>
              <h2 style={{ ...typography.heading, marginBottom: spacing.sm }}>Загрузите фото чека</h2>
              <p style={{ ...typography.body, color: colors.textSecondary }}>
                Лучше крупно, без наклона и с видимой строкой ИТОГ.
              </p>
            </div>
          </div>

          <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileUpload} style={{ display: 'none' }} />

          <Card interactive onClick={() => fileInputRef.current?.click()} style={{ cursor: 'pointer' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md }}>
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: borderRadius.lg,
                  background: colors.secondaryBg,
                  color: colors.primary,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 26,
                  fontWeight: 900,
                }}
              >
                +
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ ...typography.subtitle }}>Выбрать фото</div>
                <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 3 }}>
                  JPG, PNG или HEIC из галереи
                </div>
              </div>
              <div style={{ color: colors.muted, fontSize: 24 }}>›</div>
            </div>
          </Card>
        </PageContent>

        <PageFooter>
          <Button fullWidth size="lg" onClick={() => fileInputRef.current?.click()} loading={isLoading}>
            Сканировать чек
          </Button>
        </PageFooter>
      </PageContainer>
    );
  }

  if (step === 'review' && receipt) {
    return (
      <PageContainer>
        <Header
          title="Проверьте чек"
          subtitle={receipt.placeName || formatDate(receipt.paidAt)}
          onBack={() => setStep('upload')}
          rightAction={<Pill tone={totalDelta <= 0.02 ? 'green' : 'yellow'}>{totalDelta <= 0.02 ? 'сошлось' : 'есть разница'}</Pill>}
        />

        <PageContent>
          {isLoading && <Loading label="Сохраняю..." />}
          {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}
          {renderToast()}

          <Card elevated>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md, alignItems: 'flex-start' }}>
              <div>
                <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750, textTransform: 'uppercase' }}>
                  {receipt.placeName || 'Место не распознано'}
                </div>
                <div style={{ ...typography.title, fontSize: 30, marginTop: 5 }}>{rub(receipt.totalSum)}</div>
                <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 3 }}>{formatDate(receipt.paidAt)}</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm, alignItems: 'flex-end' }}>
                <Pill tone={suspiciousCount > 0 ? 'yellow' : 'green'}>
                  {suspiciousCount > 0 ? `${suspiciousCount} проверить` : 'чисто'}
                </Pill>
                <Pill tone="blue">{receipt.items.length} поз.</Pill>
              </div>
            </div>
          </Card>

          <ReceiptSummary items={receipt.items} tip={receipt.tip} service={receipt.service} expectedTotal={receipt.totalSum} />

          {receiptPreviewUrl && (
            <Card
              interactive
              onClick={() => setIsPreviewOpen(true)}
              style={{ cursor: 'pointer', minHeight: 132, display: 'flex', alignItems: 'center' }}
            >
              <div style={{ display: 'grid', gridTemplateColumns: '74px 1fr auto', gap: spacing.md, alignItems: 'center' }}>
                <img
                  src={receiptPreviewUrl}
                  alt="Фото чека"
                  style={{
                    width: 74,
                    height: 92,
                    objectFit: 'cover',
                    borderRadius: borderRadius.md,
                    border: `1px solid ${colors.divider}`,
                    background: colors.surfaceAlt,
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <div style={{ ...typography.subtitle }}>Оригинал чека</div>
                  <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 3 }}>
                    Откройте фото, чтобы сверить спорные строки
                  </div>
                </div>
                <div style={{ color: colors.muted, fontSize: 24 }}>›</div>
              </div>
            </Card>
          )}

          <Card>
            <Input
              label="Ваше имя в комнате"
              placeholder="Например: Дима"
              value={creatorName}
              onChange={(e) => setCreatorName(e.target.value)}
            />
          </Card>

          <div>
            <div style={{ ...typography.subtitle, marginBottom: spacing.sm }}>Позиции</div>
            <ReceiptItemList items={receipt.items} mode="edit" onEditItem={startEditItem} onDeleteItem={handleDeleteItem} />
          </div>

          <Card>
            <div style={{ ...typography.subtitle, marginBottom: spacing.md }}>Добавить позицию</div>
            <div style={{ display: 'grid', gap: spacing.sm }}>
              <Input label="Название" placeholder="например: Паста" value={newItemName} onChange={(e) => setNewItemName(e.target.value)} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 92px', gap: spacing.sm }}>
                <Input label="Цена" type="number" inputMode="decimal" placeholder="0.00" value={newItemPrice} onChange={(e) => setNewItemPrice(e.target.value)} />
                <Input label="Кол-во" type="number" inputMode="decimal" value={newItemQty} onChange={(e) => setNewItemQty(e.target.value)} />
              </div>
              <Button onClick={handleAddItem} loading={isLoading} fullWidth variant="secondary">
                Добавить
              </Button>
            </div>
          </Card>
        </PageContent>

        <PageFooter>
          <Button fullWidth size="lg" onClick={handleCreateRoom} loading={isLoading}>
            Разделить с другом
          </Button>
        </PageFooter>

        {editingItem && (
          <BottomSheet onClose={cancelEditItem}>
            <div style={{ ...typography.heading, marginBottom: spacing.md }}>Правка позиции</div>
            <div style={{ display: 'grid', gap: spacing.sm }}>
              <Input label="Название" value={editItemName} onChange={(e) => setEditItemName(e.target.value)} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 96px', gap: spacing.sm }}>
                <Input label="Цена" type="number" inputMode="decimal" step="0.01" value={editItemPrice} onChange={(e) => setEditItemPrice(e.target.value)} />
                <Input label="Кол-во" type="number" inputMode="decimal" step="0.001" value={editItemQty} onChange={(e) => setEditItemQty(e.target.value)} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm, marginTop: spacing.sm }}>
                <Button fullWidth onClick={handleSaveEditedItem} loading={isLoading}>Сохранить</Button>
                <Button fullWidth variant="secondary" onClick={cancelEditItem} disabled={isLoading}>Отмена</Button>
              </div>
            </div>
          </BottomSheet>
        )}

        {isPreviewOpen && receiptPreviewUrl && (
          <BottomSheet onClose={() => setIsPreviewOpen(false)}>
            <div style={{ ...typography.heading, marginBottom: spacing.md }}>Оригинал чека</div>
            <div
              style={{
                maxHeight: '68vh',
                overflow: 'auto',
                borderRadius: borderRadius.lg,
                background: colors.surfaceAlt,
                border: `1px solid ${colors.divider}`,
              }}
            >
              <img
                src={receiptPreviewUrl}
                alt="Оригинальное фото чека"
                style={{
                  display: 'block',
                  width: '100%',
                  height: 'auto',
                }}
              />
            </div>
          </BottomSheet>
        )}
      </PageContainer>
    );
  }

  if (step === 'share') {
    return (
      <PageContainer>
        <Header title="Комната готова" subtitle="Отправьте код второму участнику" />

        <PageContent>
          {renderToast()}
          <Card elevated style={{ textAlign: 'center', padding: 24 }}>
            <Pill tone="green">активна</Pill>
            <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750, marginTop: 20, textTransform: 'uppercase' }}>
              Код комнаты
            </div>
            <button
              onClick={copyCode}
              style={{
                marginTop: spacing.sm,
                width: '100%',
                background: colors.text,
                color: '#fff',
                borderRadius: 22,
                padding: '18px 12px',
                fontSize: 34,
                fontWeight: 900,
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                letterSpacing: 3,
                cursor: 'pointer',
              }}
            >
              {shareCode}
            </button>
            <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: spacing.sm }}>
              Тапните по коду, чтобы скопировать
            </div>
          </Card>

          <div>
            <div style={{ ...typography.subtitle, marginBottom: spacing.sm }}>Мини-чек</div>
            <ReceiptSummary items={receipt?.items || []} expectedTotal={receipt?.totalSum} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm }}>
            <Card style={{ padding: spacing.md }}>
              <div style={{ ...typography.caption, color: colors.textSecondary }}>Позиции</div>
              <div style={{ ...typography.heading }}>{receipt?.items.length || 0}</div>
            </Card>
            <Card style={{ padding: spacing.md }}>
              <div style={{ ...typography.caption, color: colors.textSecondary }}>Итого</div>
              <div style={{ ...typography.heading }}>{rub(receipt?.totalSum || 0)}</div>
            </Card>
          </div>
        </PageContent>

        <PageFooter>
          <div style={{ display: 'grid', gap: spacing.sm }}>
            <Button fullWidth size="lg" variant="secondary" onClick={shareRoom}>
              Поделиться в Telegram
            </Button>
            <Button fullWidth size="lg" onClick={() => setCurrentPage('select-items')}>
              Выбрать свои позиции
            </Button>
            <Button fullWidth size="lg" variant="secondary" onClick={() => setCurrentPage('home')}>
              На главную
            </Button>
          </div>
        </PageFooter>
      </PageContainer>
    );
  }

  return null;
};
