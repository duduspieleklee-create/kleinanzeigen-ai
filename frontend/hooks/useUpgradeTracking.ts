import { useEffect } from 'react';

export const useUpgradeTracking = (event: string, data: Record<string, any> = {}) => {
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', event, data);
    }
  }, [event, data]);
};

export const trackUpgradeClick = (plan: string, variant: 'A' | 'B') => {
  useUpgradeTracking('upgrade_click', { plan, variant });
};

export const trackCheckoutStart = (plan: string, paymentMethod: string) => {
  useUpgradeTracking('checkout_start', { plan, paymentMethod });
};
