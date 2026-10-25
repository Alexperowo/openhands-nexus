export interface ConversationItem {
  id: string;
  title: string | null;
  execution_status?: string | null;
  created_at: string;
  updated_at: string;
}
