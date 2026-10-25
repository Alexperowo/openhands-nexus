// Replaces Canvas's ui/dropdown/clear-button.js: same button, but its spoken name comes from
// the dictionary (Canvas hard-codes "Clear selection" although the key exists).
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

export function ClearButton({ onClear }: { onClear: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" data-testid="dropdown-clear" onClick={onClear} aria-label={t("COMMON$CLEAR_SELECTION")}
      className="text-contrast hover:text-text-tertiary">
      <X size={14} />
    </button>
  );
}
