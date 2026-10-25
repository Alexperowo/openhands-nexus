import React from "react";
import { useTranslation } from "react-i18next";
// The original component; vite.config.ts routes every other import of it to this adapter.
import { ToggleButton as CanvasToggleButton } from "../node_modules/@openhands/agent-canvas/dist/ui/dropdown/toggle-button.js";

type Props = React.ComponentProps<typeof CanvasToggleButton>;

// The Canvas list arrow is an icon-only button, so TalkBack reads it as "button" with
// no name (axe button-name). The name goes in through the props downshift builds.
export function ToggleButton(props: Props) {
  const { t } = useTranslation();
  const label = t("NEXUS$SHOW_OPTIONS");
  return (
    <CanvasToggleButton {...props}
      getToggleButtonProps={(options) => props.getToggleButtonProps({ ...options, "aria-label": label })} />
  );
}
