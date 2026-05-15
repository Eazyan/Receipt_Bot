import React, { useState } from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import { PageContainer, PageContent, PageFooter, Button, Header, Card, Pill } from '@/components/UI';
import { useAppStore } from '@/hooks/useAppStore';
import { hapticFeedback, showTelegramAlert } from '@/utils/telegram';

const rub = (value: number) => `${value.toFixed(2)} ₽`;

export const ResultsPage: React.FC = () => {
  const { currentRoom, currentParticipantId, paymentSplits, setCurrentPage, clearCurrentRoom, clearSelection } = useAppStore();
  const [copied, setCopied] = useState(false);

  if (!currentRoom) {
    return (
      <PageContainer>
        <PageContent>
          <Card>Нет данных по комнате</Card>
        </PageContent>
      </PageContainer>
    );
  }

  const settledSplits = paymentSplits || [];
  const payableSplits = settledSplits.filter((split) => split.userId !== 'unassigned');
  const unassignedSplit = settledSplits.find((split) => split.userId === 'unassigned');
  const payer = payableSplits.find((split) => split.userId === currentRoom.creatorId) || payableSplits[0];
  const you = payableSplits.find((split) => split.userId === currentParticipantId) || payer || payableSplits[0];
  const isPayer = Boolean(you && payer && you.userId === payer.userId);
  const transferRows = isPayer
    ? payableSplits
      .filter((split) => split.userId !== payer?.userId && split.total > 0)
      .map((split) => ({
        key: split.userId,
        title: split.username,
        subtitle: `за ${split.items.length} поз.`,
        amount: split.total,
      }))
    : you && payer && you.total > 0
      ? [{
        key: `${you.userId}-${payer.userId}`,
        title: payer.username,
        subtitle: 'получатель перевода',
        amount: you.total,
      }]
      : [];
  const transferLines = isPayer
    ? transferRows.map((row) => `${row.title} должен вам ${rub(row.amount)}`)
    : transferRows.map((row) => `Вы должны ${row.title} ${rub(row.amount)}`);
  const transferText = unassignedSplit && unassignedSplit.total > 0
    ? `Осталось распределить ${rub(unassignedSplit.total)}`
    : transferLines.length > 0
      ? transferLines.length === 1 ? transferLines[0] : `${transferLines.length} перевода к вам`
      : 'Суммы равны';
  const transferTotal = transferRows.reduce((sum, row) => sum + row.amount, 0);

  const handleNewRoom = () => {
    clearCurrentRoom();
    clearSelection();
    setCurrentPage('home');
  };

  const copyResult = async () => {
    const text = [
      'Разделение чека',
      ...settledSplits.map((split) => `${split.username}: ${rub(split.total)}`),
      ...(transferLines.length > 0 ? ['', 'Переводы:', ...transferLines] : []),
      transferText,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      hapticFeedback('success');
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      showTelegramAlert(text);
    }
  };

  return (
    <PageContainer>
      <Header title="Готово" subtitle={transferText} />

      <PageContent>
        {copied && <Pill tone="dark" style={{ justifyContent: 'center' }}>Итог скопирован</Pill>}

        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            background: `linear-gradient(145deg, ${colors.primaryDark}, ${colors.text})`,
            borderRadius: 28,
            padding: 24,
            minHeight: 232,
            color: '#fff',
            boxShadow: '0 22px 46px rgba(23,33,43,0.2)',
          }}
        >
          {[0, 1, 2, 3, 4, 5].map((index) => (
            <span
              key={index}
              style={{
                position: 'absolute',
                top: `${8 + index * 13}%`,
                right: `${8 + (index % 3) * 24}%`,
                width: 5 + (index % 2) * 3,
                height: 18,
                borderRadius: 999,
                background: 'rgba(255,255,255,0.2)',
                transform: `rotate(${index * 23}deg)`,
                animation: `confettiDrift ${2.8 + index * 0.2}s ease-in-out infinite`,
              }}
            />
          ))}
          <span
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: '-42%',
              width: '36%',
              transform: 'skewX(-18deg)',
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)',
              animation: 'shineSweep 3.8s ease-in-out infinite',
            }}
          />
          <div style={{ position: 'relative', zIndex: 1 }}>
          <Pill tone="dark" style={{ background: 'rgba(255,255,255,0.14)', color: '#fff' }}>ваша доля</Pill>
          <div style={{ fontSize: 46, lineHeight: 1.05, fontWeight: 900, marginTop: 16 }}>
            {rub(you?.total || 0)}
          </div>
          <div style={{ ...typography.body, color: 'rgba(255,255,255,0.72)', marginTop: 8 }}>
            {you?.items.length || 0} позиций в вашем выборе
          </div>
          {transferTotal > 0 && (
            <div
              style={{
                marginTop: spacing.lg,
                padding: spacing.md,
                borderRadius: borderRadius.lg,
                background: 'rgba(255,255,255,0.12)',
                border: '1px solid rgba(255,255,255,0.18)',
              }}
            >
              <div style={{ ...typography.caption, color: 'rgba(255,255,255,0.68)', marginBottom: 4 }}>
                {isPayer ? 'К получению' : 'К переводу'}
              </div>
              <div style={{ ...typography.subtitle, color: '#fff' }}>{rub(transferTotal)}</div>
            </div>
          )}
          </div>
        </div>

        {transferRows.length > 0 && (
          <Card elevated>
            <div style={{ ...typography.subtitle, marginBottom: spacing.md }}>{isPayer ? 'Кто переводит' : 'Кому перевести'}</div>
            <div style={{ display: 'grid', gap: spacing.sm }}>
              {transferRows.map((row) => (
                <div
                  key={row.key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr auto',
                    gap: spacing.sm,
                    alignItems: 'center',
                    padding: spacing.md,
                    borderRadius: borderRadius.md,
                    background: colors.secondaryBg,
                  }}
                >
                  <div>
                    <div style={{ ...typography.bodySmall, fontWeight: 850 }}>{row.title}</div>
                    <div style={{ ...typography.caption, color: colors.textSecondary }}>{row.subtitle}</div>
                  </div>
                  <div style={{ ...typography.subtitle, color: colors.primary }}>{rub(row.amount)}</div>
                </div>
              ))}
            </div>
          </Card>
        )}

        <div style={{ display: 'grid', gap: spacing.md }}>
          {settledSplits.map((split, idx) => (
            <Card key={split.userId || idx} elevated={idx === 0}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md }}>
                <div>
                  <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750 }}>
                    {split.username || `Участник ${idx + 1}`}
                  </div>
                  <div style={{ ...typography.heading, marginTop: 4 }}>{rub(split.total)}</div>
                </div>
                <Pill tone={split.userId === 'unassigned' ? 'red' : idx === 0 ? 'blue' : 'yellow'}>{split.items.length} поз.</Pill>
              </div>

              {split.items.length > 0 && (
                <div style={{ display: 'grid', gap: spacing.sm, marginTop: spacing.md }}>
                  {split.items.slice(0, 5).map((item, itemIndex) => (
                    <div
                      key={`${item.name}-${itemIndex}`}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: spacing.md,
                        background: colors.background,
                        borderRadius: borderRadius.md,
                        padding: spacing.sm,
                      }}
                    >
                      <span style={{ ...typography.bodySmall, color: colors.text, minWidth: 0 }}>{item.name}</span>
                      <span style={{ ...typography.bodySmall, fontWeight: 800, whiteSpace: 'nowrap' }}>
                        {rub(item.subtotal)}
                      </span>
                    </div>
                  ))}
                  {split.items.length > 5 && (
                    <div style={{ ...typography.caption, color: colors.textSecondary }}>
                      Ещё {split.items.length - 5} позиций
                    </div>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>

        <Card>
          <div style={{ ...typography.subtitle, marginBottom: spacing.md }}>Сводка</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.sm }}>
            <div style={{ background: colors.background, borderRadius: borderRadius.md, padding: spacing.md }}>
              <div style={{ ...typography.caption, color: colors.textSecondary }}>Чек</div>
              <div style={{ ...typography.subtitle }}>{rub(currentRoom.receipt?.totalSum || 0)}</div>
            </div>
            <div style={{ background: colors.background, borderRadius: borderRadius.md, padding: spacing.md }}>
              <div style={{ ...typography.caption, color: colors.textSecondary }}>Код</div>
              <div style={{ ...typography.subtitle }}>{currentRoom.shareCode || currentRoom.id}</div>
            </div>
          </div>
        </Card>
      </PageContent>

      <PageFooter>
        <div style={{ display: 'grid', gap: spacing.sm }}>
          <Button fullWidth size="lg" onClick={copyResult}>
            Скопировать итог
          </Button>
          <Button fullWidth size="lg" variant="secondary" onClick={handleNewRoom}>
            Новый чек
          </Button>
        </div>
      </PageFooter>
    </PageContainer>
  );
};
