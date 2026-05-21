import React, { useState, useRef, useCallback } from 'react';
import { colors, spacing, typography } from '@/styles/theme';
import {
  PageContainer,
  PageContent,
  PageFooter,
  Header,
  ErrorAlert,
  Card,
  Button,
  Pill,
} from '@/components/UI';
import { useAppStore } from '@/hooks/useAppStore';
import { hapticFeedback } from '@/utils/telegram';
import { asrAPI } from '@/utils/api';

type RecordingState = 'idle' | 'recording' | 'uploading';

export const RoomPage: React.FC = () => {
  const { setCurrentPage, currentRoom } = useAppStore();

  const [textInput, setTextInput] = useState('');
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcription, setTranscription] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const startRecording = useCallback(async () => {
    try {
      setError(null);
      setTranscription(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const preferredMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
        ? 'audio/ogg;codecs=opus'
        : '';

      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      const mimeType = recorder.mimeType || preferredMimeType || 'audio/webm';
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const audioBlob = new Blob(chunksRef.current, { type: mimeType });
        await sendToASR(audioBlob, mimeType);
      };

      recorder.start(250);
      mediaRecorderRef.current = recorder;
      setRecordingState('recording');
      setRecordingSeconds(0);

      timerRef.current = setInterval(() => {
        setRecordingSeconds((s) => s + 1);
      }, 1000);

      hapticFeedback('impact');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Нет доступа к микрофону';
      setError(msg);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setRecordingState('uploading');
    hapticFeedback('success');
  }, []);

  const handleMicToggle = () => {
    if (recordingState === 'recording') stopRecording();
    else if (recordingState === 'idle') startRecording();
  };

  const handleSendText = () => {
    if (!textInput.trim()) return;
    console.log('[Room] Текстовый запрос:', textInput);
    setCurrentPage('select-items');
  };

  const sendToASR = async (blob: Blob, mimeType: string) => {
    try {
      const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';

      console.log('[ASR] Отправка аудио на сервер...', { size: blob.size, type: mimeType });

      const text = await asrAPI.transcribe(blob, `recording.${ext}`);
      console.log('[ASR] Результат:', text);
      setTranscription(text);
      setTextInput((prev) => (prev ? prev + ' ' + text : text));
      hapticFeedback('success');
    } catch (err) {
      console.error('[ASR] Ошибка:', err);
      setError(err instanceof Error ? err.message : 'Ошибка распознавания');
      hapticFeedback('impact');
    } finally {
      setRecordingState('idle');
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const roomCode = currentRoom?.shareCode ?? currentRoom?.id?.slice(0, 6).toUpperCase() ?? '------';
  const isRecording = recordingState === 'recording';
  const isUploading = recordingState === 'uploading';

  return (
    <PageContainer>
      <Header title="Комната" subtitle="Голосом или вручную" onBack={() => setCurrentPage('home')} rightAction={<Pill tone="blue">{roomCode}</Pill>} />

      <PageContent>
        {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

        <div
          style={{
            background: `linear-gradient(145deg, ${colors.primaryDark}, ${colors.text})`,
            borderRadius: 28,
            padding: 22,
            color: '#fff',
            boxShadow: '0 22px 46px rgba(23,33,43,0.2)',
          }}
        >
          <Pill tone="dark" style={{ background: 'rgba(255,255,255,0.14)', color: '#fff' }}>voice split</Pill>
          <div style={{ ...typography.title, color: '#fff', marginTop: 18 }}>
            Скажите, что было вашим
          </div>
          <div style={{ ...typography.body, color: 'rgba(255,255,255,0.72)', marginTop: 8 }}>
            Например: “кофе мне, пакет пополам”. Или выберите позиции вручную.
          </div>
        </div>

        {transcription && (
          <Card>
            🎙 Распознано: «{transcription}»
          </Card>
        )}

        {isRecording && (
          <Card style={{ background: colors.errorSoft, borderColor: 'rgba(229,72,77,0.18)', display: 'flex', alignItems: 'center', gap: spacing.sm }}>
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: colors.error,
                boxShadow: `0 0 0 4px rgba(232,107,107,0.25)`,
                flexShrink: 0,
              }}
            />
            <span style={{ ...typography.body, color: colors.error, fontWeight: 600 }}>
              Запись {formatTime(recordingSeconds)}
            </span>
          </Card>
        )}

        {isUploading && (
          <Card style={{ background: colors.warningSoft }}>
            ⏳ Распознаём речь...
          </Card>
        )}

        <Card
          interactive
          onClick={() => setCurrentPage('select-items')}
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md }}
        >
          <div>
            <div style={{ ...typography.subtitle, color: colors.text, marginBottom: 4 }}>
              Выбрать вручную
            </div>
            <div style={{ ...typography.bodySmall, color: colors.textSecondary }}>
              Отметьте позиции из чека
            </div>
          </div>
          <div style={{ fontSize: '22px', color: colors.primary }}>→</div>
        </Card>
      </PageContent>

      <PageFooter>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
        <input
          ref={inputRef}
          type="text"
          placeholder={isRecording ? 'Идёт запись...' : 'Что вы заказывали?'}
          value={isRecording ? '' : textInput}
          onChange={(e) => !isRecording && setTextInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSendText()}
          disabled={isRecording || isUploading}
          style={{
            flex: 1,
            height: '42px',
            borderRadius: '21px',
            border: `1.5px solid ${isRecording ? colors.error : colors.border}`,
            backgroundColor: isRecording ? '#FFF0EE' : colors.secondaryBg,
            padding: `0 ${spacing.md}px`,
            ...typography.body,
            color: colors.text,
            outline: 'none',
            transition: 'border-color 0.2s',
          }}
        />

        {/* Send button — shown only when text is ready */}
        {textInput.trim() && !isRecording && !isUploading && (
          <Button onClick={handleSendText} aria-label="Отправить" style={{ width: 42, height: 42, minHeight: 42, padding: 0, borderRadius: '50%', flexShrink: 0 }}>
            →
          </Button>
        )}

        {/* Mic button */}
        <button
          onClick={handleMicToggle}
          disabled={isUploading}
          style={{
            width: '42px', height: '42px', borderRadius: '50%',
            border: 'none', outline: 'none',
            cursor: isUploading ? 'not-allowed' : 'pointer',
            backgroundColor: isRecording ? colors.error : colors.primary,
            color: '#fff', fontSize: '20px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            boxShadow: isRecording ? `0 0 0 5px rgba(232,107,107,0.25)` : `0 2px 8px ${colors.shadow}`,
            transition: 'all 0.2s ease',
          }}
          aria-label={isRecording ? 'Остановить запись' : 'Голосовой ввод'}
        >
          {isUploading ? '⏳' : isRecording ? '⏹' : '🎙'}
        </button>
        </div>
      </PageFooter>
    </PageContainer>
  );
};
