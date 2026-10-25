import type { ComponentProps } from "react";
import { ModalBackdrop as CanvasModalBackdrop } from "../node_modules/@openhands/agent-canvas/dist/components/shared/modals/modal-backdrop.js";
import { BaseModalTitle } from "../node_modules/@openhands/agent-canvas/dist/components/shared/modals/confirmation-modals/base-modal.js";
import { dialogLabel } from "./dialog-label";

type Props = ComponentProps<typeof CanvasModalBackdrop>;

export function ModalBackdrop(props: Props) {
  return <CanvasModalBackdrop {...props} aria-label={props["aria-label"] ?? dialogLabel(props.children, BaseModalTitle)} />;
}
