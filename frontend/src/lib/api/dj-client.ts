import { request } from "./base";
import type {
  DJConversationResponse,
  DJConversationDetailResponse,
  DJMessageResponse,
  DJProvidersResponse,
} from "@/types/api";

export const fetchConversations = () =>
  request<DJConversationResponse[]>("/dj/conversations");

export const createConversation = (title: string = "New Conversation") =>
  request<DJConversationResponse>("/dj/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });

export const fetchConversation = (id: string) =>
  request<DJConversationDetailResponse>(`/dj/conversations/${id}`);

export const deleteConversation = (id: string) =>
  request<{ deleted: boolean }>(`/dj/conversations/${id}`, { method: "DELETE" });

export const sendDJMessage = (conversationId: string, content: string) =>
  request<{
    message: DJMessageResponse;
    generation_job_id: string | null;
    fallback_notice: string | null;
  }>(`/dj/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });

export const fetchDJProviders = () =>
  request<DJProvidersResponse>("/dj/providers");

export const updateDJSettings = (settings: {
  provider?: string;
  model?: string;
  system_prompt?: string;
  api_key?: string;
  api_base?: string;
}) =>
  request<DJProvidersResponse>("/dj/settings", {
    method: "PATCH",
    body: JSON.stringify(settings),
  });

export const renameConversation = (id: string, title: string) =>
  request<{ renamed: boolean }>(`/dj/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export const installCloudPackages = () =>
  request<{ message: string }>("/dj/install-cloud-packages", {
    method: "POST",
  });
