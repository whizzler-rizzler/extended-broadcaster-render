const API_BASE = import.meta.env.VITE_API_BASE || '';

export const getApiUrl = (path: string): string => {
  return `${API_BASE}${path}`;
};

export const getWsUrl = (path: string): string => {
  if (API_BASE) {
    return API_BASE.replace('https://', 'wss://').replace('http://', 'ws://') + path;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${path}`;
};

export { API_BASE };
