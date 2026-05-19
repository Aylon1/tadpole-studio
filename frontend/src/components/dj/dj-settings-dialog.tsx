"use client";

import { useState, useCallback, useEffect } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchDJProviders, updateDJSettings } from "@/lib/api/dj-client";

interface DJSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DJSettingsDialog({ open, onOpenChange }: DJSettingsDialogProps) {
  const {
    data: providers,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["dj-providers"],
    queryFn: fetchDJProviders,
    enabled: open,
  });

  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // Sync local state when data loads or changes
  useEffect(() => {
    if (providers) {
      setSelectedProvider(providers.active_provider);
      setSelectedModel(providers.active_model);
      setSystemPrompt(
        providers.system_prompt || providers.default_system_prompt,
      );
    }
  }, [providers]);

  const activeProviderInfo = providers?.providers.find(
    (p) => p.name === selectedProvider,
  );

  const availableModels = activeProviderInfo?.models ?? [];

  const handleProviderChange = useCallback(
    (value: string) => {
      setSelectedProvider(value);
      const newProvider = providers?.providers.find((p) => p.name === value);
      const firstModel = newProvider?.models[0] ?? "";
      setSelectedModel(firstModel);
    },
    [providers],
  );

  const handleResetPrompt = useCallback(() => {
    if (providers) {
      setSystemPrompt(providers.default_system_prompt);
    }
  }, [providers]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      await updateDJSettings({
        provider: selectedProvider,
        model: selectedModel,
        system_prompt: systemPrompt,
      });
      toast.success("DJ settings updated");
      await refetch();
      onOpenChange(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to update settings";
      toast.error(message);
    }
    setIsSaving(false);
  }, [selectedProvider, selectedModel, systemPrompt, refetch, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>DJ Settings</DialogTitle>
          <DialogDescription>
            Configure the LLM provider and model for the AI DJ.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4 overflow-y-auto flex-1 pr-1">
            {/* Provider selector */}
            <div className="space-y-2">
              <Label htmlFor="provider-select">Provider</Label>
              <Select
                value={selectedProvider}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger id="provider-select">
                  <SelectValue placeholder="Select a provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers?.providers.map((provider) => (
                    <SelectItem key={provider.name} value={provider.name}>
                      <span className="flex items-center gap-2">
                        {provider.name}
                        {!provider.available && (
                          <Badge variant="outline" className="text-[10px] text-red-700 dark:text-red-500 border-red-500/20">
                            Unavailable
                          </Badge>
                        )}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Availability status */}
            {activeProviderInfo && (
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={
                    activeProviderInfo.available
                      ? "border-green-500/20 bg-green-500/10 text-green-700 dark:text-green-500"
                      : "border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-500"
                  }
                >
                  {activeProviderInfo.available ? "Available" : "Unavailable"}
                </Badge>
              </div>
            )}

            {/* Unavailability reason hint */}
            {activeProviderInfo && !activeProviderInfo.available && activeProviderInfo.unavailable_reason && (
              <div className="flex items-start gap-2 rounded-md bg-blue-500/10 p-3 text-sm text-blue-600 dark:text-blue-400">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{activeProviderInfo.unavailable_reason}</span>
              </div>
            )}

            {/* API key notice — only show when no key is stored */}
            {activeProviderInfo?.requires_api_key && !activeProviderInfo.has_stored_api_key && (
              <div className="flex items-start gap-2 rounded-md bg-yellow-500/10 p-3 text-sm text-yellow-600 dark:text-yellow-500">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  This provider requires an API key. Add one on the{" "}
                  <a href="/models" className="underline underline-offset-2 hover:text-yellow-700 dark:hover:text-yellow-400">
                    Models
                  </a>{" "}
                  page.
                </span>
              </div>
            )}

            {/* API base notice for OpenAI Compatible */}
            {activeProviderInfo?.name === "openai-compatible" && !activeProviderInfo.has_api_base && (
              <div className="flex items-start gap-2 rounded-md bg-yellow-500/10 p-3 text-sm text-yellow-600 dark:text-yellow-500">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  This provider requires an API base URL. Configure it on the{" "}
                  <a href="/models" className="underline underline-offset-2 hover:text-yellow-700 dark:hover:text-yellow-400">
                    Models
                  </a>{" "}
                  page.
                </span>
              </div>
            )}

            <Separator />

            {/* Model selector */}
            <div className="space-y-2">
              <Label htmlFor="model-select">Model</Label>
              <Select
                value={selectedModel}
                onValueChange={setSelectedModel}
              >
                <SelectTrigger id="model-select">
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {availableModels.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No models available for this provider.
                </p>
              )}
            </div>

            <Separator />

            {/* System prompt */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="system-prompt">System Prompt</Label>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-auto px-2 py-1 text-xs text-muted-foreground"
                  onClick={handleResetPrompt}
                >
                  Reset to default
                </Button>
              </div>
              <Textarea
                id="system-prompt"
                rows={6}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                className="font-mono text-xs"
                placeholder="Enter a custom system prompt for the DJ..."
              />
              <p className="text-xs text-muted-foreground">
                Customize how the AI DJ behaves and responds.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving || isLoading || !selectedProvider || !selectedModel}
          >
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
