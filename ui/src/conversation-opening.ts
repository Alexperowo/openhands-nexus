export const NEW_CONVERSATION_SELECTOR = 'a[data-testid="sidebar-conversations-link"]';
type OpeningPath = "/" | "/conversations";
type Operation = { id: number; path: OpeningPath };
type OpeningState = { nextId: number; requested: Operation | null; opening: Operation | null };

export function isOpeningPath(path: string): path is OpeningPath {
  return path === "/" || path === "/conversations";
}

export function initialOpening(path: string): OpeningState {
  return { nextId: 1, requested: isOpeningPath(path) ? { id: 0, path } : null, opening: null };
}

export function requestOpening(state: OpeningState, path: string): OpeningState {
  if (!isOpeningPath(path) || state.opening?.path === path) return state;
  return { ...state, nextId: state.nextId + 1, requested: { id: state.nextId, path } };
}

export function beginOpening(state: OpeningState, path: string) {
  if (state.opening || state.requested?.path !== path) return { state, operation: null };
  const operation = state.requested;
  return { state: { ...state, requested: null, opening: operation }, operation };
}

export function finishOpening(state: OpeningState, operation: Operation): OpeningState {
  return state.opening?.id === operation.id ? { ...state, opening: null } : state;
}

export function mayShowOpened(state: OpeningState, operation: Operation, path: string) {
  return state.opening?.id === operation.id && !state.requested && operation.path === path;
}

type Activation = {
  button: number; metaKey: boolean; altKey: boolean; ctrlKey: boolean; shiftKey: boolean;
  defaultPrevented: boolean;
};

export function isNewConversationClick(event: Activation, link: { target: string; disabled: boolean }) {
  return event.button === 0 && !event.defaultPrevented && !event.metaKey && !event.altKey &&
    !event.ctrlKey && !event.shiftKey && (!link.target || link.target === "_self") && !link.disabled;
}
