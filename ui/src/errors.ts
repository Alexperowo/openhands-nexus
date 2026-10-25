/** Browser errors arrive in English and in technical terms; show what happened instead. */
export function errorMessage(error: unknown, service = "Сервер") {
  if (error instanceof DOMException && error.name === "TimeoutError") return `${service} не ответил вовремя. Попробуйте ещё раз.`;
  if (error instanceof TypeError) return `${service} недоступен. Проверьте, что компьютер включён и в сети.`;
  return error instanceof Error ? error.message : "Не удалось выполнить запрос";
}
