import React, { useEffect } from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import { PageContainer, PageContent, PageFooter, Button, Card, Pill } from '@/components/UI';
import { useAppStore } from '@/hooks/useAppStore';
import { hapticFeedback } from '@/utils/telegram';

const quickStats = [
  { label: 'OCR', value: 'AI', tone: colors.secondaryBg },
  { label: 'split', value: '50/50', tone: colors.warningSoft },
  { label: 'TG', value: 'share', tone: colors.successSoft },
];

export const HomePage: React.FC = () => {
  const { setCurrentPage, currentRoom } = useAppStore();

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
  }, []);

  const goCreate = () => {
    hapticFeedback('selection');
    setCurrentPage('create-room');
  };

  return (
    <PageContainer>
      <PageContent>
        <div
          style={{
            background: `linear-gradient(145deg, ${colors.text} 0%, #25384D 55%, ${colors.primaryDark} 100%)`,
            borderRadius: 26,
            padding: 22,
            color: '#fff',
            overflow: 'hidden',
            position: 'relative',
            minHeight: 252,
            boxShadow: '0 22px 46px rgba(23,33,43,0.22)',
          }}
        >
          <div
            style={{
              position: 'absolute',
              right: -28,
              top: -24,
              width: 148,
              height: 148,
              borderRadius: 48,
              background: 'rgba(255,255,255,0.09)',
              transform: 'rotate(18deg)',
            }}
          />
          <div
            style={{
              position: 'absolute',
              right: 24,
              bottom: 18,
              width: 106,
              height: 142,
              borderRadius: 14,
              background: '#fff',
              color: colors.text,
              padding: 12,
              boxShadow: '0 18px 34px rgba(0,0,0,0.22)',
              transform: 'rotate(5deg)',
            }}
          >
            <div style={{ height: 7, width: 48, borderRadius: 999, background: colors.border, marginBottom: 10 }} />
            {[0, 1, 2, 3].map((idx) => (
              <div key={idx} style={{ display: 'flex', gap: 5, marginBottom: 8 }}>
                <div style={{ height: 6, flex: 1, borderRadius: 999, background: idx === 1 ? colors.warningSoft : colors.surfaceAlt }} />
                <div style={{ height: 6, width: 22, borderRadius: 999, background: idx === 2 ? colors.successSoft : colors.border }} />
              </div>
            ))}
            <div style={{ height: 1, background: colors.divider, margin: '12px 0' }} />
            <div style={{ fontSize: 15, fontWeight: 900 }}>1 248 ₽</div>
          </div>

          <Pill tone="dark" style={{ backgroundColor: 'rgba(255,255,255,0.14)', color: '#fff' }}>
            Telegram mini app
          </Pill>
          <h1 style={{ ...typography.title, color: '#fff', maxWidth: 230, marginTop: 18 }}>
            Раздели чек за минуту
          </h1>
          <p style={{ ...typography.body, color: 'rgba(255,255,255,0.74)', maxWidth: 230, marginTop: 10 }}>
            Сканируй, правь спорные строки и отправляй другу код комнаты.
          </p>
          <div style={{ display: 'flex', gap: spacing.sm, marginTop: 22 }}>
            {quickStats.map((stat) => (
              <div
                key={stat.label}
                style={{
                  background: 'rgba(255,255,255,0.13)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: borderRadius.md,
                  padding: '9px 10px',
                  minWidth: 64,
                }}
              >
                <div style={{ fontSize: 15, fontWeight: 850 }}>{stat.value}</div>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.62)', marginTop: 2 }}>{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
          <Card interactive style={{ padding: spacing.md }}>
            <div style={{ fontSize: 24, marginBottom: spacing.sm }}>▣</div>
            <div style={{ ...typography.subtitle }}>AI-чек</div>
            <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 4 }}>
              Находит позиции, цены и количество
            </div>
          </Card>
          <Card interactive style={{ padding: spacing.md }}>
            <div style={{ fontSize: 24, marginBottom: spacing.sm }}>↔</div>
            <div style={{ ...typography.subtitle }}>Быстрый split</div>
            <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 4 }}>
              Мне, другу или пополам в один тап
            </div>
          </Card>
        </div>

        {currentRoom?.receipt && (
          <Card elevated interactive>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md }}>
              <div>
                <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750 }}>
                  Последняя комната
                </div>
                <div style={{ ...typography.subtitle, marginTop: 4 }}>
                  {currentRoom.shareCode || `#${currentRoom.id}`}
                </div>
              </div>
              <Button size="sm" onClick={() => setCurrentPage('select-items')}>
                Открыть
              </Button>
            </div>
          </Card>
        )}
      </PageContent>

      <PageFooter>
        <div style={{ display: 'grid', gap: spacing.sm }}>
          <Button fullWidth size="lg" onClick={goCreate}>
            Сканировать чек
          </Button>
          <Button fullWidth size="lg" variant="secondary" onClick={() => setCurrentPage('room-code')}>
            Войти по коду
          </Button>
        </div>
      </PageFooter>
    </PageContainer>
  );
};
