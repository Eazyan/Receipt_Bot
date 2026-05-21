import React, { useEffect, useMemo, useRef, useState } from 'react';
import { PageContainer, PageContent, PageFooter, Button, Header, Loading, ErrorAlert, Card, Pill, Input, ReceiptSkeleton } from '@/components/UI';
import { ReceiptItemList, getReceiptSubtotal } from '@/components/ReceiptItems';
import { useAppStore } from '@/hooks/useAppStore';
import { asrAPI, roomAPI, WS_BASE_URL } from '@/utils/api';
import { hapticFeedback, showTelegramAlert } from '@/utils/telegram';
import { colors, spacing, typography, borderRadius } from '@/styles/theme';
import type { ItemCategory, ItemIntelligence, PaymentSplit, ReceiptItem, SplitParticipant, SplitMode, SplitProposal } from '@/types';

const rub = (value: number) => `${value.toFixed(2)} ₽`;

const roundQty = (value: number) => Number(Math.max(0, value).toFixed(3));

const sumItemSplits = (splits: Record<string, number> | undefined) =>
  Object.values(splits || {}).reduce((sum, qty) => sum + qty, 0);

const participantTotal = (items: ReceiptItem[], itemSplits: Record<string, Record<string, number>>, participantId: string) =>
  items.reduce((sum, item) => sum + item.price * (itemSplits[item.id]?.[participantId] || 0), 0);

const participantSelectedCount = (items: ReceiptItem[], itemSplits: Record<string, Record<string, number>>, participantId: string) =>
  items.filter((item) => (itemSplits[item.id]?.[participantId] || 0) > 0).length;

const buildPaymentSplits = (
  items: ReceiptItem[],
  itemSplits: Record<string, Record<string, number>>,
  participants: SplitParticipant[],
): PaymentSplit[] => {
  const splits = participants.map((participant) => {
    const splitItems = items
      .map((item) => {
        const quantity = itemSplits[item.id]?.[participant.id] || 0;
        return {
          name: item.name,
          quantity,
          price: item.price,
          subtotal: item.price * quantity,
        };
      })
      .filter((item) => item.quantity > 0);
    const subtotal = splitItems.reduce((sum, item) => sum + item.subtotal, 0);
    return {
      userId: participant.id,
      username: participant.name,
      items: splitItems,
      subtotal,
      taxShare: 0,
      tipShare: 0,
      total: subtotal,
    };
  });

  const unassignedItems = items
    .map((item) => {
      const assigned = sumItemSplits(itemSplits[item.id]);
      const quantity = roundQty(item.quantity - assigned);
      return {
        name: item.name,
        quantity,
        price: item.price,
        subtotal: item.price * quantity,
      };
    })
    .filter((item) => item.quantity > 0);

  if (unassignedItems.length > 0) {
    const subtotal = unassignedItems.reduce((sum, item) => sum + item.subtotal, 0);
    splits.push({
      userId: 'unassigned',
      username: 'Не распределено',
      items: unassignedItems,
      subtotal,
      taxShare: 0,
      tipShare: 0,
      total: subtotal,
    });
  }

  return splits;
};

export const SelectItemsPage: React.FC = () => {
  const {
    currentRoom,
    setCurrentPage,
    clearSelection,
    setError: setAppError,
    error,
    setError,
    setPaymentSplits,
    splitParticipants,
    currentParticipantId,
    itemSplits,
    liveProposals,
    liveSplitMode,
    liveCreatorParticipantId,
    applyLiveRoomState,
  } = useAppStore();
  const [isLoading, setIsLoading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(true);
  const [syncStatus, setSyncStatus] = useState<'connecting' | 'live' | 'fallback' | 'error'>('connecting');
  const [searchQuery, setSearchQuery] = useState('');
  const [commandText, setCommandText] = useState('');
  const [commandStatus, setCommandStatus] = useState<string | null>(null);
  const [isCommandLoading, setIsCommandLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isVoiceUploading, setIsVoiceUploading] = useState(false);
  const [itemIntelligence, setItemIntelligence] = useState<Record<string, ItemIntelligence>>({});
  const [isIntelligenceLoading, setIsIntelligenceLoading] = useState(false);
  const reconnectTimerRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceTimeoutRef = useRef<number | null>(null);

  const receipt = currentRoom?.receipt;
  const currentParticipant = splitParticipants.find((participant) => participant.id === currentParticipantId);
  const splitMode = liveSplitMode;

  useEffect(() => {
    if (!currentRoom?.id || !currentParticipantId) return undefined;

    let closed = false;
    let socket: WebSocket | null = null;

    const fetchState = async () => {
      try {
        const state = await roomAPI.getState(currentRoom.id, currentParticipantId);
        if (!closed) {
          applyLiveRoomState(state);
          setSyncStatus('fallback');
          setIsSyncing(false);
        }
      } catch {
        if (!closed) {
          setSyncStatus('error');
          setIsSyncing(false);
        }
      }
    };

    const connect = () => {
      if (closed) return;
      setSyncStatus('connecting');
      socket = new WebSocket(`${WS_BASE_URL}/rooms/${currentRoom.id}/ws?participantId=${encodeURIComponent(currentParticipantId)}`);

      socket.onopen = () => {
        if (!closed) setSyncStatus('live');
      };

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'state') {
            applyLiveRoomState(message.state);
            setIsSyncing(false);
            setSyncStatus('live');
          }
        } catch {
          setSyncStatus('error');
        }
      };

      socket.onerror = () => {
        if (!closed) setSyncStatus('fallback');
      };

      socket.onclose = () => {
        if (closed) return;
        setSyncStatus('fallback');
        fetchState();
        reconnectTimerRef.current = window.setTimeout(connect, 1200);
      };
    };

    fetchState();
    connect();

    return () => {
      closed = true;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      socket?.close();
    };
  }, [applyLiveRoomState, currentParticipantId, currentRoom?.id]);

  useEffect(() => () => {
    if (voiceTimeoutRef.current) {
      window.clearTimeout(voiceTimeoutRef.current);
      voiceTimeoutRef.current = null;
    }
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    voiceStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!currentRoom?.id || !currentParticipantId || !receipt?.items.length) {
      setItemIntelligence({});
      return undefined;
    }

    let cancelled = false;
    setIsIntelligenceLoading(true);
    roomAPI.getItemIntelligence(currentRoom.id, currentParticipantId)
      .then((items) => {
        if (cancelled) return;
        setItemIntelligence(Object.fromEntries(items.map((item) => [item.id, item])));
      })
      .catch(() => {
        if (!cancelled) setItemIntelligence({});
      })
      .finally(() => {
        if (!cancelled) setIsIntelligenceLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentParticipantId, currentRoom?.id, receipt?.items.length]);

  const totals = useMemo(() => {
    if (!receipt) return { receiptTotal: 0, expectedTotal: 0, difference: 0, distributedTotal: 0, unassignedTotal: 0 };
    const receiptTotal = getReceiptSubtotal(receipt.items);
    const expectedTotal = receipt.totalSum > 0 ? receipt.totalSum : receiptTotal;
    const distributedTotal = splitParticipants.reduce(
      (sum, participant) => sum + participantTotal(receipt.items, itemSplits, participant.id),
      0,
    );
    return {
      receiptTotal,
      expectedTotal,
      difference: Number((receiptTotal - expectedTotal).toFixed(2)),
      distributedTotal,
      unassignedTotal: Math.max(0, receiptTotal - distributedTotal),
    };
  }, [itemSplits, receipt, splitParticipants]);

  if (!currentRoom || !receipt || !currentParticipant) {
    return (
      <PageContainer>
        <PageContent>
          <Loading fullScreen label="Подключаю вас к комнате..." />
        </PageContent>
      </PageContainer>
    );
  }

  const activeSelectedItems = Object.fromEntries(
    receipt.items.map((item) => [item.id, itemSplits[item.id]?.[currentParticipant.id] || 0]),
  );

  const normalizedSearch = searchQuery.trim().toLowerCase();
  const visibleItems = normalizedSearch
    ? receipt.items.filter((item) => item.name.toLowerCase().includes(normalizedSearch))
    : receipt.items;

  const reconciliationTone = Math.abs(totals.difference) <= 0.02 ? 'green' : Math.abs(totals.difference) <= 10 ? 'yellow' : 'red';
  const reconciliationText = Math.abs(totals.difference) <= 0.02
    ? 'позиции сходятся'
    : totals.difference > 0
      ? `позиции больше на ${rub(Math.abs(totals.difference))}`
      : `не хватает ${rub(Math.abs(totals.difference))}`;

  const getMaxForActive = (item: ReceiptItem) => {
    const itemMap = itemSplits[item.id] || {};
    const activeQty = itemMap[currentParticipant.id] || 0;
    const allocatedByOthers = sumItemSplits(itemMap) - activeQty;
    return roundQty(item.quantity - allocatedByOthers);
  };

  const getAllocated = (item: ReceiptItem) => sumItemSplits(itemSplits[item.id]);

  const getUnallocated = (item: ReceiptItem) => roundQty(item.quantity - getAllocated(item));

  const getAllocationSummary = (item: ReceiptItem) =>
    Object.entries(itemSplits[item.id] || {})
      .map(([participantId, quantity]) => {
        const participant = splitParticipants.find((candidate) => candidate.id === participantId);
        return {
          name: participant?.id === currentParticipant.id ? 'Вы' : participant?.name ?? 'Участник',
          quantity,
          amount: item.price * quantity,
          isCurrent: participantId === currentParticipant.id,
        };
      })
      .filter((allocation) => allocation.quantity > 0);

  const participantName = (participantId: string) =>
    splitParticipants.find((participant) => participant.id === participantId)?.name ?? 'Участник';

  const getOfferTargets = (item: ReceiptItem) =>
    getUnallocated(item) > 0
      ? splitParticipants
        .filter((participant) => participant.id !== currentParticipant.id)
        .map((participant) => ({ id: participant.id, name: participant.name }))
      : [];

  const getSuggestion = (item: ReceiptItem) => {
    const currentQuantity = itemSplits[item.id]?.[currentParticipant.id] || 0;
    if (currentQuantity > 0 || getUnallocated(item) <= 0) return null;
    const intelligence = itemIntelligence[item.id];
    if (!intelligence?.suggest_for_participant || intelligence.suggestion_confidence < 0.72) return null;
    return intelligence.matched_history_item
      ? `Похоже на ваше: ${intelligence.matched_history_item}`
      : 'Похоже, это снова ваше';
  };

  const getCategory = (item: ReceiptItem): ItemCategory => {
    const intelligence = itemIntelligence[item.id];
    if (!intelligence || intelligence.category_confidence < 0.55) return 'other';
    return intelligence.category;
  };

  const applyAction = async (action: Record<string, unknown>) => {
    if (!currentRoom) return;
    try {
      const state = await roomAPI.applyStateAction(currentRoom.id, action, currentParticipant.id);
      applyLiveRoomState(state);
      setSyncStatus('live');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось синхронизировать';
      setError(message);
      setSyncStatus('error');
      hapticFeedback('impact');
    }
  };

  const setActiveQuantity = (itemId: string, quantity: number) => {
    const item = receipt.items.find((candidate) => candidate.id === itemId);
    if (!item) return;
    const maxQuantity = getMaxForActive(item);
    applyAction({
      type: 'set_quantity',
      itemId,
      quantity: roundQty(Math.min(quantity, maxQuantity)),
    });
  };

  const assignAllToActive = (item: ReceiptItem) => {
    setActiveQuantity(item.id, getMaxForActive(item));
    hapticFeedback('selection');
  };

  const splitHalfItem = (item: ReceiptItem) => {
    const participantIds = splitParticipants.map((participant) => participant.id);
    if (participantIds.length < 2) {
      showTelegramAlert('Добавьте второго участника');
      return;
    }
    applyAction({
      type: 'propose_split',
      proposalType: 'split_item_evenly',
      itemId: item.id,
      fromParticipantId: currentParticipant.id,
      participantIds,
    });
    hapticFeedback('selection');
  };

  const offerItemToParticipant = (item: ReceiptItem, targetParticipantId: string) => {
    const quantity = getUnallocated(item);
    if (quantity <= 0) return;
    applyAction({
      type: 'propose_claim',
      itemId: item.id,
      fromParticipantId: currentParticipant.id,
      targetParticipantId,
      quantity,
    });
    hapticFeedback('selection');
  };

  const splitAllEvenly = () => {
    const participantIds = splitParticipants.map((participant) => participant.id);
    if (participantIds.length < 2) {
      showTelegramAlert('Добавьте второго участника');
      return;
    }
    applyAction({
      type: 'propose_split',
      proposalType: 'split_all_evenly',
      fromParticipantId: currentParticipant.id,
      participantIds,
    });
    hapticFeedback('success');
  };

  const runAssistantCommand = async (rawCommand = commandText) => {
    const command = rawCommand.trim();
    if (!command) {
      setCommandStatus('Напишите команду для агента.');
      hapticFeedback('impact');
      return;
    }
    setIsCommandLoading(true);
    setCommandStatus('Думаю...');
    try {
      const result = await roomAPI.runAssistantCommand(currentRoom.id, currentParticipant.id, command);
      applyLiveRoomState(result.state);
      setSyncStatus('live');
      setCommandStatus(result.message || 'Готово.');
      setCommandText('');
      hapticFeedback(result.actions.length > 0 ? 'success' : 'impact');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Агент не смог выполнить команду';
      setCommandStatus(message);
      setError(message);
      hapticFeedback('impact');
    } finally {
      setIsCommandLoading(false);
    }
  };

  const startVoiceCommand = () => {
    if (isListening) {
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setCommandStatus('Голосовой ввод недоступен в этом WebView. Используйте текстовую команду.');
      hapticFeedback('impact');
      return;
    }

    const preferredMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
      ? 'audio/ogg;codecs=opus'
      : '';

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        const recorder = preferredMimeType
          ? new MediaRecorder(stream, { mimeType: preferredMimeType })
          : new MediaRecorder(stream);
        const mimeType = recorder.mimeType || preferredMimeType || 'audio/webm';
        voiceStreamRef.current = stream;
        voiceChunksRef.current = [];
        mediaRecorderRef.current = recorder;

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) voiceChunksRef.current.push(event.data);
        };

        recorder.onerror = () => {
          setCommandStatus('Не удалось записать голос.');
          hapticFeedback('impact');
        };

        recorder.onstop = () => {
          if (voiceTimeoutRef.current) {
            window.clearTimeout(voiceTimeoutRef.current);
            voiceTimeoutRef.current = null;
          }
          stream.getTracks().forEach((track) => track.stop());
          voiceStreamRef.current = null;
          setIsListening(false);

          const audioBlob = new Blob(voiceChunksRef.current, { type: mimeType });
          voiceChunksRef.current = [];
          if (!audioBlob.size) {
            setCommandStatus('Голос не записался. Попробуйте ещё раз.');
            hapticFeedback('impact');
            return;
          }

          const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
          setIsVoiceUploading(true);
          setCommandStatus('Распознаю голос...');
          asrAPI.transcribe(audioBlob, `command.${ext}`)
            .then((text) => {
              setCommandText(text);
              setCommandStatus(`Распознано: ${text}`);
              return runAssistantCommand(text);
            })
            .catch((err) => {
              const message = err instanceof Error ? err.message : 'Не удалось распознать голос';
              setCommandStatus(message);
              setError(message);
              hapticFeedback('impact');
            })
            .finally(() => {
              setIsVoiceUploading(false);
            });
        };

        recorder.start(250);
        setIsListening(true);
        setCommandStatus('Запись... нажмите микрофон ещё раз, чтобы отправить.');
        voiceTimeoutRef.current = window.setTimeout(() => {
          if (mediaRecorderRef.current?.state === 'recording') {
            mediaRecorderRef.current.stop();
          }
        }, 18000);
        hapticFeedback('impact');
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : 'Нет доступа к микрофону';
        setCommandStatus(message);
        setError(message);
        hapticFeedback('impact');
      });
  };

  const isSplitModeOwner = currentParticipant.id === (liveCreatorParticipantId || currentRoom.creatorId);

  const setRoomSplitMode = (mode: SplitMode) => {
    if (!isSplitModeOwner) return;
    applyAction({ type: 'set_split_mode', splitMode: mode });
    hapticFeedback('selection');
  };

  const modeMeta: Record<SplitMode, { title: string; description: string }> = {
    even: {
      title: 'Поровну',
      description: 'Предложите всем участникам равный split по каждой позиции.',
    },
    items: {
      title: 'По позициям',
      description: 'Каждый забирает только свои товары. Самый точный режим.',
    },
    mixed: {
      title: 'Смешанный',
      description: 'Можно забирать себе, предлагать другим и делить спорные позиции.',
    },
  };

  const assignAllReceiptToActive = () => {
    applyAction({ type: 'claim_all_available' });
    hapticFeedback('selection');
  };

  const clearCurrentParticipantSelection = () => {
    applyAction({ type: 'clear_participant' });
  };

  const canSeeProposal = (proposal: SplitProposal) => {
    if (proposal.fromParticipantId === currentParticipant.id) return true;
    return proposal.participantIds.includes(currentParticipant.id);
  };

  const openProposals = liveProposals.filter((proposal) => proposal.status === 'open' && canSeeProposal(proposal));

  const proposalTitle = (proposal: SplitProposal) => {
    if (proposal.type === 'split_all_evenly') {
      return proposal.fromParticipantId === currentParticipant.id
        ? 'Вы предложили поделить весь чек'
        : `${participantName(proposal.fromParticipantId)} предлагает поделить весь чек`;
    }
    const item = receipt.items.find((candidate) => candidate.id === proposal.itemId);
    if (proposal.type === 'claim_item') {
      if (proposal.fromParticipantId === currentParticipant.id) {
        return `Вы предложили ${participantName(proposal.targetParticipantId ?? '')} забрать "${item?.name ?? 'позицию'}"`;
      }
      return `${participantName(proposal.fromParticipantId)} предлагает вам забрать "${item?.name ?? 'позицию'}"`;
    }
    return proposal.fromParticipantId === currentParticipant.id
      ? `Вы предложили поделить "${item?.name ?? 'позицию'}"`
      : `${participantName(proposal.fromParticipantId)} предлагает поделить "${item?.name ?? 'позицию'}"`;
  };

  const proposalStatusText = (proposal: SplitProposal) => {
    if (proposal.acceptedBy.length > 0) {
      return `Согласились: ${proposal.acceptedBy.map(participantName).join(', ')}`;
    }
    if (proposal.type === 'claim_item' && proposal.fromParticipantId === currentParticipant.id) {
      return `Ждём ответ: ${participantName(proposal.targetParticipantId ?? '')}`;
    }
    return 'Ожидает ответа';
  };

  const acceptProposal = (proposal: SplitProposal) => {
    applyAction({ type: 'accept_proposal', proposalId: proposal.id, participantId: currentParticipant.id });
    hapticFeedback('success');
  };

  const declineProposal = (proposal: SplitProposal) => {
    applyAction({ type: 'decline_proposal', proposalId: proposal.id, participantId: currentParticipant.id });
    hapticFeedback('impact');
  };

  const handleSubmitSelection = async () => {
    const paymentSplits = buildPaymentSplits(receipt.items, itemSplits, splitParticipants);
    const hasAnyDistribution = paymentSplits.some((split) => split.userId !== 'unassigned' && split.total > 0);
    if (!hasAnyDistribution) {
      showTelegramAlert('Распределите хотя бы одну позицию');
      hapticFeedback('impact');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      setPaymentSplits(paymentSplits);
      await Promise.all(
        paymentSplits
          .filter((split) => split.userId === currentParticipant.id)
          .map((split) => roomAPI.rememberItemHistory(
            currentRoom.id,
            split.userId,
            split.items.map((item) => ({
              name: item.name,
              quantity: item.quantity,
              category: getCategory(
                receipt.items.find((receiptItem) => receiptItem.name === item.name && receiptItem.price === item.price)
                || { id: '', assignedUsers: [], name: item.name, price: item.price, quantity: item.quantity },
              ),
            })),
          )),
      );
      hapticFeedback('success');
      setCurrentPage('results');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка при расчете';
      setAppError(message);
      hapticFeedback('impact');
      showTelegramAlert(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <PageContainer>
      <Header
        title="Кому что?"
        subtitle={receipt.placeName || `${receipt.items.length} позиций`}
        onBack={() => {
          clearSelection();
          setCurrentPage('home');
        }}
        rightAction={<Pill tone={totals.unassignedTotal <= 0.01 ? 'green' : 'yellow'}>{rub(totals.receiptTotal)}</Pill>}
      />

      <PageContent>
        {isLoading && <Loading label="Считаю split..." />}
        {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

        <Card elevated>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md, alignItems: 'center', marginBottom: spacing.md }}>
            <div>
              <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750 }}>Активный участник</div>
              <div style={{ ...typography.heading, marginTop: 2 }}>Вы: {currentParticipant.name}</div>
            </div>
            <Pill tone={totals.unassignedTotal <= 0.01 ? 'green' : 'yellow'}>
              {totals.unassignedTotal <= 0.01 ? 'всё распределено' : `осталось ${rub(totals.unassignedTotal)}`}
            </Pill>
          </div>
          <div style={{ marginBottom: spacing.md }}>
            <Pill tone={syncStatus === 'live' ? 'green' : syncStatus === 'error' ? 'red' : 'yellow'}>
              {syncStatus === 'live' ? 'live sync' : syncStatus === 'connecting' ? 'подключение...' : syncStatus === 'fallback' ? 'REST fallback' : 'нет связи'}
            </Pill>
          </div>

          <div style={{ display: 'flex', gap: spacing.sm, overflowX: 'auto', paddingBottom: 2 }}>
            {splitParticipants.map((participant) => {
              const total = participantTotal(receipt.items, itemSplits, participant.id);
              const isActive = participant.id === currentParticipant.id;
              return (
                <div
                  key={participant.id}
                  style={{
                    minWidth: 126,
                    borderRadius: borderRadius.lg,
                    padding: spacing.md,
                    background: isActive ? colors.text : colors.background,
                    color: isActive ? '#fff' : colors.text,
                    textAlign: 'left',
                    border: `1px solid ${isActive ? colors.text : colors.divider}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.sm }}>
                    <span style={{ ...typography.bodySmall, fontWeight: 850 }}>{participant.name}</span>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: participant.color, marginTop: 5 }} />
                  </div>
                  <div style={{ ...typography.subtitle, marginTop: 8 }}>{rub(total)}</div>
                  <div style={{ ...typography.caption, color: isActive ? 'rgba(255,255,255,0.62)' : colors.textSecondary }}>
                    {participantSelectedCount(receipt.items, itemSplits, participant.id)} поз.
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <div style={{ ...typography.subtitle, marginBottom: spacing.sm }}>Режим разделения</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: spacing.xs }}>
            {(['even', 'items', 'mixed'] as SplitMode[]).map((mode) => {
              const selected = splitMode === mode;
              return (
                <button
                  key={mode}
                  onClick={() => {
                    setRoomSplitMode(mode);
                  }}
                  disabled={!isSplitModeOwner}
                  style={{
                    minHeight: 42,
                    borderRadius: borderRadius.md,
                    background: selected ? colors.text : colors.surfaceAlt,
                    color: selected ? '#fff' : colors.text,
                    fontWeight: 850,
                    opacity: !isSplitModeOwner && !selected ? 0.62 : 1,
                    cursor: isSplitModeOwner ? 'pointer' : 'default',
                  }}
                >
                  {modeMeta[mode].title}
                </button>
              );
            })}
          </div>
          <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: spacing.sm }}>
            {isSplitModeOwner ? modeMeta[splitMode].description : `Режим задаёт создатель комнаты. Сейчас: ${modeMeta[splitMode].title}.`}
          </div>
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: spacing.sm }}>
          <Button size="sm" variant={splitMode === 'even' ? 'primary' : 'secondary'} onClick={splitAllEvenly}>
            Предложить всем
          </Button>
          <Button size="sm" variant="secondary" onClick={assignAllReceiptToActive}>
            Всё себе
          </Button>
          <Button size="sm" variant="ghost" onClick={clearCurrentParticipantSelection}>
            Сбросить своё
          </Button>
        </div>

        {splitMode === 'even' && isSplitModeOwner && (
          <Card style={{ borderColor: 'rgba(47,128,237,0.28)', background: colors.secondaryBg }}>
            <div style={{ ...typography.subtitle, color: colors.primary, marginBottom: 4 }}>Быстрый сценарий</div>
            <div style={{ ...typography.bodySmall, color: colors.textSecondary, marginBottom: spacing.md }}>
              Если все согласны делить чек поровну, отправьте одно предложение всем участникам.
            </div>
            <Button fullWidth onClick={splitAllEvenly}>Предложить равный split</Button>
          </Card>
        )}

        <Card>
          <div style={{ ...typography.subtitle, marginBottom: spacing.sm }}>Командный помощник</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 46px', gap: spacing.sm }}>
            <Input
              aria-label="Команда распределения"
              placeholder="Например: кофе мне, салат Маше"
              value={commandText}
              onChange={(event) => {
                setCommandText(event.target.value);
                setCommandStatus(null);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void runAssistantCommand();
              }}
              disabled={isCommandLoading || isVoiceUploading}
            />
            <Button
              aria-label={isListening ? 'Остановить запись' : 'Голосовая команда'}
              variant={isListening ? 'danger' : 'secondary'}
              onClick={startVoiceCommand}
              disabled={isCommandLoading || isVoiceUploading}
              loading={isVoiceUploading}
              style={{ minWidth: 46, paddingLeft: 0, paddingRight: 0, alignSelf: 'end' }}
            >
              {isListening ? '■' : '🎙'}
            </Button>
          </div>
          <Button fullWidth variant="ghost" onClick={() => void runAssistantCommand()} disabled={!commandText.trim() || isCommandLoading || isVoiceUploading || isListening} loading={isCommandLoading} style={{ marginTop: spacing.sm }}>
            Выполнить команду
          </Button>
          {commandStatus && (
            <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: spacing.sm }}>
              {commandStatus}
            </div>
          )}
        </Card>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Pill tone={isIntelligenceLoading ? 'yellow' : 'green'}>
            {isIntelligenceLoading ? 'AI анализирует чек' : 'AI категории готовы'}
          </Pill>
        </div>

        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: spacing.md, alignItems: 'center' }}>
            <div>
              <div style={{ ...typography.caption, color: colors.textSecondary, fontWeight: 750 }}>Сверка</div>
              <div style={{ ...typography.subtitle, marginTop: 3 }}>
                Позиции {rub(totals.receiptTotal)} / Итого {rub(totals.expectedTotal)}
              </div>
            </div>
            <Pill tone={reconciliationTone}>{reconciliationText}</Pill>
          </div>
          <div
            style={{
              height: 7,
              borderRadius: 999,
              background: colors.surfaceAlt,
              overflow: 'hidden',
              marginTop: spacing.md,
            }}
          >
            <div
              style={{
                width: `${Math.min(100, Math.max(4, (totals.distributedTotal / Math.max(totals.receiptTotal, 1)) * 100))}%`,
                height: '100%',
                borderRadius: 999,
                background: reconciliationTone === 'green' ? colors.success : reconciliationTone === 'yellow' ? colors.warning : colors.error,
                transition: 'width 0.2s ease',
              }}
            />
          </div>
        </Card>

        {receipt.items.length >= 6 && (
          <Input
            aria-label="Поиск по позициям"
            placeholder="Найти кофе, сыр, пиво..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            style={{
              minHeight: 44,
              borderRadius: borderRadius.lg,
              background: colors.surface,
            }}
          />
        )}

        {openProposals.length > 0 && (
          <Card>
            <div style={{ ...typography.subtitle, fontWeight: 850, marginBottom: spacing.sm }}>Предложения</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
              {openProposals.map((proposal) => {
                const accepted = proposal.acceptedBy.includes(currentParticipant.id);
                const isParticipant = proposal.participantIds.includes(currentParticipant.id);
                return (
                  <div
                    key={proposal.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr auto',
                      gap: spacing.sm,
                      alignItems: 'center',
                      padding: spacing.sm,
                      borderRadius: borderRadius.md,
                      background: colors.surfaceAlt,
                    }}
                  >
                    <div>
                      <div style={{ ...typography.bodySmall, fontWeight: 800 }}>{proposalTitle(proposal)}</div>
                      <div style={{ ...typography.caption, color: colors.textSecondary, marginTop: 2 }}>
                        {proposalStatusText(proposal)}
                      </div>
                    </div>
                    {isParticipant && !accepted ? (
                      <div style={{ display: 'flex', gap: spacing.xs }}>
                        <Button size="sm" onClick={() => acceptProposal(proposal)}>Да</Button>
                        <Button size="sm" variant="ghost" onClick={() => declineProposal(proposal)}>Нет</Button>
                      </div>
                    ) : (
                      <Pill tone={accepted ? 'green' : 'yellow'}>{accepted ? 'вы согласны' : 'ожидаем'}</Pill>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {isSyncing ? (
          <ReceiptSkeleton rows={Math.min(4, receipt.items.length || 4)} />
        ) : visibleItems.length > 0 ? (
          <ReceiptItemList
            items={visibleItems}
            selectedItems={activeSelectedItems}
            onSelectItem={setActiveQuantity}
            onAssignAll={assignAllToActive}
            onSplitHalf={splitHalfItem}
            onOfferToParticipant={offerItemToParticipant}
            mode="select"
            activeParticipantName="Вы"
            claimButtonLabel="Забрать себе"
            splitButtonLabel="Предложить"
            getOfferTargets={getOfferTargets}
            getAllocationSummary={getAllocationSummary}
            getCategory={getCategory}
            getSuggestion={getSuggestion}
            onAcceptSuggestion={assignAllToActive}
            getMaxSelectableQuantity={getMaxForActive}
            getAllocatedQuantity={getAllocated}
          />
        ) : (
          <Card style={{ textAlign: 'center' }}>
            <div style={{ ...typography.subtitle, marginBottom: spacing.xs }}>Ничего не найдено</div>
            <div style={{ ...typography.bodySmall, color: colors.textSecondary }}>Попробуйте другое название позиции</div>
          </Card>
        )}
      </PageContent>

      <PageFooter>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.35fr', gap: spacing.sm, alignItems: 'center' }}>
          <div>
            <div style={{ ...typography.caption, color: colors.textSecondary }}>Распределено</div>
            <div style={{ ...typography.heading }}>{rub(totals.distributedTotal)}</div>
          </div>
          <Button fullWidth onClick={handleSubmitSelection} loading={isLoading} disabled={totals.distributedTotal <= 0}>
            Готово
          </Button>
        </div>
      </PageFooter>
    </PageContainer>
  );
};
