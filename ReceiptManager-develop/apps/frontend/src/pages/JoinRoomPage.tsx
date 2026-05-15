import React, { useState } from 'react';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import { PageContainer, PageContent, PageFooter, Button, Input, Header, ErrorAlert, Loading, Card, Pill } from '@/components/UI';
import { useAppStore } from '@/hooks/useAppStore';
import { roomAPI } from '@/utils/api';
import { hapticFeedback, showTelegramAlert } from '@/utils/telegram';

export const JoinRoomPage: React.FC = () => {
  const { setCurrentPage, setCurrentRoom, setCurrentParticipant, applyLiveRoomState, setIsLoading, isLoading, error, setError, telegramUser } = useAppStore();
  const [code, setCode] = useState('');
  const [displayName, setDisplayName] = useState(() => {
    const saved = window.localStorage.getItem('receipt-manager-name');
    return saved || telegramUser?.first_name || '';
  });
  const [joinAsNew, setJoinAsNew] = useState(false);
  const [inputError, setInputError] = useState('');

  const getTabParticipantId = (roomId: string, forceNew: boolean) => {
    const memberKey = `receipt-manager-member:${roomId}`;
    const existing = window.sessionStorage.getItem(memberKey);
    if (existing && !forceNew) return existing;
    const participantId = `guest-${crypto.randomUUID()}`;
    window.sessionStorage.setItem(memberKey, participantId);
    return participantId;
  };

  const handleJoin = async () => {
    if (!code.trim()) {
      setInputError('Введите код комнаты');
      return;
    }
    if (!displayName.trim()) {
      setInputError('Введите ваше имя');
      return;
    }

    setIsLoading(true);
    setError(null);
    setInputError('');

    try {
      const room = await roomAPI.findByCode(code.trim());
      const participantId = getTabParticipantId(room.id, joinAsNew);
      window.localStorage.setItem('receipt-manager-name', displayName.trim());
      const state = await roomAPI.upsertSplitParticipant(room.id, participantId, displayName.trim(), '#19A974');
      setCurrentRoom(room, 'participant');
      applyLiveRoomState(state);
      setCurrentParticipant(participantId);
      hapticFeedback('success');
      setCurrentPage('select-items');
      setJoinAsNew(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось присоединиться';
      setError(message);
      setInputError('Неверный код');
      hapticFeedback('impact');
      showTelegramAlert(`Ошибка: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <PageContainer>
      <Header title="Войти по коду" subtitle="Код есть у создателя комнаты" onBack={() => setCurrentPage('home')} />

      <PageContent>
        {isLoading && <Loading fullScreen label="Ищу комнату..." />}
        {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

        <Card elevated style={{ textAlign: 'center', padding: 24 }}>
          <Pill tone="blue">guest mode</Pill>
          <div
            style={{
              width: 94,
              height: 94,
              margin: '22px auto 16px',
              borderRadius: 28,
              background: `linear-gradient(145deg, ${colors.secondaryBg}, ${colors.surface})`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 42,
              color: colors.primary,
              fontWeight: 900,
              border: `1px solid ${colors.divider}`,
            }}
          >
            #
          </div>
          <h2 style={{ ...typography.heading, marginBottom: spacing.sm }}>Введите 6 символов</h2>
          <p style={{ ...typography.body, color: colors.textSecondary }}>
            Назовитесь, чтобы остальные видели не “Друг”, а ваше имя.
          </p>
        </Card>

        <Input
          label="Ваше имя"
          placeholder="Например: Аня"
          value={displayName}
          onChange={(e) => {
            setDisplayName(e.target.value);
            setInputError('');
          }}
          disabled={isLoading}
        />

        <Input
          label="Код комнаты"
          placeholder="ABC123"
          value={code}
          onChange={(e) => {
            setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8));
            setInputError('');
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleJoin();
          }}
          error={inputError}
          disabled={isLoading}
          style={{
            textAlign: 'center',
            fontSize: 30,
            fontWeight: 900,
            letterSpacing: 4,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            minHeight: 64,
            borderRadius: borderRadius.lg,
          }}
        />

        <Button
          fullWidth
          variant={joinAsNew ? 'primary' : 'ghost'}
          onClick={() => setJoinAsNew((value) => !value)}
          disabled={isLoading}
        >
          {joinAsNew ? 'Будет создан новый участник' : 'Войти как новый участник'}
        </Button>
      </PageContent>

      <PageFooter>
        <Button fullWidth size="lg" onClick={handleJoin} loading={isLoading}>
          Присоединиться
        </Button>
      </PageFooter>
    </PageContainer>
  );
};
