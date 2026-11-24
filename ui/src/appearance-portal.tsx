import type { ComponentProps } from "react";
import { AppearancePortal as CanvasAppearancePortal } from "../node_modules/@openhands/agent-canvas/dist/components/shared/appearance-portal.js";

// Canvas styles and Nexus theme overrides are scoped to this root.
export function AppearancePortal(props: ComponentProps<typeof CanvasAppearancePortal>) {
  if (typeof document === "undefined") return null;
  const container = props.container ?? document.querySelector<HTMLElement>("[data-agent-server-ui]");
  return <CanvasAppearancePortal {...props} container={container ?? undefined} />;
}
