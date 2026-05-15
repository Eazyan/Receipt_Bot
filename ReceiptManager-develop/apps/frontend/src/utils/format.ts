export const formatCurrency = (amount: number, currency: string = 'RUB'): string => {
  const symbols: Record<string, string> = {
    RUB: '₽',
    USD: '$',
    EUR: '€',
    GBP: '£',
  };

  const symbol = symbols[currency] || currency;
  
  return `${amount.toFixed(2)} ${symbol}`;
};

export const formatCurrencyCompact = (amount: number, currency: string = 'RUB'): string => {
  const symbols: Record<string, string> = {
    RUB: '₽',
    USD: '$',
    EUR: '€',
    GBP: '£',
  };

  const symbol = symbols[currency] || currency;
  
  return `${amount.toFixed(0)}${symbol}`;
};

export const calculateSubtotal = (items: Array<{ price: number; quantity: number }>): number => {
  return items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
};

export const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

export const formatTime = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  });
};

export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    console.error('Failed to copy:', err);
    return false;
  }
};

export const generateInviteLink = (baseUrl: string, roomCode: string): string => {
  return `${baseUrl}?code=${roomCode}`;
};
