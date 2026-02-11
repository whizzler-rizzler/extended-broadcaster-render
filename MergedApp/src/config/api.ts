const API_BASE = import.meta.env.VITE_API_BASE || '';

export const getApiUrl = (path: string): string => {
  return `${path}`;
};

export const getWsUrl = (path: string): string => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${path}`;
};

export { API_BASE };
