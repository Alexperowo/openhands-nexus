import React from "react";

export interface NavigationContextValue {
  currentPath: string;
  conversationId: string | null;
  isNavigating: boolean;
  navigate: (to: string, options?: { replace?: boolean }) => void;
}

export const NavigationContext = React.createContext<NavigationContextValue>({
  currentPath: "/",
  conversationId: null,
  isNavigating: false,
  navigate: () => {},
});

export function NavigationProvider({
  value,
  children,
}: {
  value: NavigationContextValue;
  children: React.ReactNode;
}) {
  return (
    <NavigationContext.Provider value={value}>
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation(): NavigationContextValue {
  return React.useContext(NavigationContext);
}
