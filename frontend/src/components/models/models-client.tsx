"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, Cpu, Download, ExternalLink, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { fetchModels, fetchAvailableModels, switchLmModel, downloadModel } from "@/lib/api/client";
import { fetchDJProviders, updateDJSettings, installCloudPackages } from "@/lib/api/dj-client";
import { useActiveBackend } from "@/hooks/use-active-backend";
import { useEngineSwitchStore } from "@/stores/engine-switch-store";
import type { ModelInfo } from "@/types/api";
import { ModelCards } from "./model-cards";
import { LoraSection } from "./lora-section";
import { GpuStats } from "./gpu-stats";

const CHAT_LLM_DESCRIPTIONS: Record<string, string> = {
  "Qwen2.5-1.5B-Instruct-4bit":
    "Recommended. Strong instruction following for its size. 869 MB.",
  "Qwen3-0.6B-4bit":
    "Ultra-lightweight alternative. 335 MB.",
};

/** Extract numeric size (e.g. 0.6, 1.7, 4) from LM model name for sorting */
function parseLmSize(name: string): number {
  const match = name.match(/([\d.]+)B$/);
  return match ? parseFloat(match[1]) : Infinity;
}

function pickSmallestLm(lmModels: ModelInfo[]): ModelInfo | undefined {
  if (lmModels.length === 0) return undefined;
  return [...lmModels].sort((a, b) => parseLmSize(a.name) - parseLmSize(b.name))[0];
}

export function ModelsClient() {
  const queryClient = useQueryClient();
  const { activeBackend, isReady, isLoading: backendsLoading } = useActiveBackend();
  const switchingTo = useEngineSwitchStore((s) => s.switchingTo);
  const clearSwitch = useEngineSwitchStore((s) => s.clearSwitch);

  // Auto-clear optimistic switch state when target backend becomes active and ready
  useEffect(() => {
    if (switchingTo && activeBackend === switchingTo && isReady) {
      clearSwitch();
    }
  }, [switchingTo, activeBackend, isReady, clearSwitch]);

  const { data: models, isLoading } = useQuery({
    queryKey: ["models"],
    queryFn: fetchModels,
  });

  const djProvidersQuery = useQuery({
    queryKey: ["dj-providers"],
    queryFn: fetchDJProviders,
    retry: false,
  });

  const [savingField, setSavingField] = useState<'url' | 'model' | 'key' | null>(null);

  const djSettingsMutation = useMutation({
    mutationFn: updateDJSettings,
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["dj-providers"], data);
      setSavingField(null);
      
      if (variables.api_key) return;
      const activeProvider = data.providers.find(
        (p) => p.name === data.active_provider
      );
      if (activeProvider && !activeProvider.available) {
        const reason = activeProvider.unavailable_reason;
        toast.warning(
          reason || `Provider "${data.active_provider}" is unavailable. DJ will try other available providers as fallback.`
        );
      } else {
        toast.success("DJ settings saved");
      }
    },
    onError: (err: Error) => {
      setSavingField(null);
      toast.error(`Failed to save DJ settings: ${err.message}`);
    },
  });

  const [isInstallingPackages, setIsInstallingPackages] = useState(false);

  const handleInstallCloudPackages = async () => {
    setIsInstallingPackages(true);
    try {
      const result = await installCloudPackages();
      toast.success(result.message);
      queryClient.invalidateQueries({ queryKey: ["dj-providers"] });
    } catch (err) {
      toast.error(
        `Install failed: ${err instanceof Error ? err.message : "Unknown error"}`
      );
    } finally {
      setIsInstallingPackages(false);
    }
  };

  // Which provider tab is currently being viewed (not necessarily the active one)
  const [viewingProvider, setViewingProvider] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiBaseInput, setApiBaseInput] = useState("");
  const [customModelInput, setCustomModelInput] = useState("");

  useEffect(() => {
    if (!djProvidersQuery.data) return;
    const exists = djProvidersQuery.data.providers.some(
      (p) => p.name === viewingProvider
    );
    if (!exists) {
      setViewingProvider(djProvidersQuery.data.active_provider);
    }
  }, [djProvidersQuery.data, viewingProvider]);

  // Handle auto-filling values when switching tabs
  useEffect(() => {
    setApiKeyInput("");
    if (djProvidersQuery.data && viewingProvider) {
      const provider = djProvidersQuery.data.providers.find(p => p.name === viewingProvider);
      if (provider) {
        setApiBaseInput(provider.api_base || "");
      }
      
      if (djProvidersQuery.data.active_provider === viewingProvider) {
        setCustomModelInput(djProvidersQuery.data.active_model || "");
      } else {
        setCustomModelInput("");
      }
    } else {
      setApiBaseInput("");
      setCustomModelInput("");
    }
  }, [viewingProvider]); // Removed djProvidersQuery.data from deps to avoid overwriting user typing on background refetch

  const handleSelectDJModel = (provider: string, model: string) => {
    djSettingsMutation.mutate({ provider, model });
  };

  const djDownloadMutation = useMutation({
    mutationFn: downloadModel,
    onSuccess: (_data, name) => {
      toast.success(`Download started for ${name}`);
      queryClient.invalidateQueries({ queryKey: ["available-models"] });
    },
    onError: (err: Error) => toast.error(`Download failed: ${err.message}`),
  });

  const { data: available } = useQuery({
    queryKey: ["available-models"],
    queryFn: fetchAvailableModels,
    refetchInterval: (query) =>
      query.state.data?.models.some((m) => m.downloading) ? 3_000 : 30_000,
  });

  // Track which models were downloading on the previous poll cycle
  const prevDownloadingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!available) return;

    const currentDownloading = new Set(
      available.models.filter((m) => m.downloading).map((m) => m.name),
    );
    const prev = prevDownloadingRef.current;

    for (const name of prev) {
      if (!currentDownloading.has(name)) {
        const model = available.models.find((m) => m.name === name);
        if (model?.installed) {
          toast.success(`Downloaded ${name} successfully`);
          queryClient.invalidateQueries({ queryKey: ["models"] });
        } else {
          toast.error(`Download failed for ${name}`);
        }
      }
    }

    prevDownloadingRef.current = currentDownloading;
  }, [available, queryClient]);

  const ditAvailable = available?.models.filter((m) => m.model_type === "dit") ?? [];
  const lmAvailable = available?.models.filter((m) => m.model_type === "lm") ?? [];
  const chatLlmAvailable = available?.models.filter((m) => m.model_type === "chat_llm") ?? [];
  const heartmulaAvailable = available?.models.filter((m) => m.model_type === "heartmula") ?? [];

  // When switching to ACE-Step and no LM model is active, auto-select the smallest installed one
  const [autoSelectingLm, setAutoSelectingLm] = useState<string | null>(null);

  const autoSelectLm = useCallback(async () => {
    const lmModels = models?.lm_models ?? [];
    if (lmModels.length === 0 || lmModels.some((m) => m.is_active)) return;

    const smallest = pickSmallestLm(lmModels);
    if (!smallest) return;

    setAutoSelectingLm(smallest.name);
    try {
      await switchLmModel(smallest.name);
      queryClient.invalidateQueries({ queryKey: ["models"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
    } catch {
      // Silent fail — user can manually select
    } finally {
      setAutoSelectingLm(null);
    }
  }, [models, queryClient]);

  // Don't show engine badges until the backends query has resolved
  // to avoid flashing ACE-Step as active when HeartMuLa was last used
  const isAceStepActive = !backendsLoading && activeBackend === "ace-step";
  const isHeartmulaActive = !backendsLoading && activeBackend === "heartmula";
  const isSwitchingToAceStep = switchingTo === "ace-step";
  const isSwitchingToHeartmula = switchingTo === "heartmula";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Cpu className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-semibold">Models</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {isLoading ? (
            <>
              <Skeleton className="h-48 w-full rounded-xl" />
              <Skeleton className="h-48 w-full rounded-xl" />
            </>
          ) : (
            <>
              {/* ACE-Step engine group */}
              <Card className={isAceStepActive ? "border-primary/50" : ""}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between text-lg">
                    ACE-Step
                    {isSwitchingToAceStep ? (
                      <Badge variant="outline" className="text-yellow-500 border-yellow-500/30 gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Loading...
                      </Badge>
                    ) : isAceStepActive ? (
                      isReady ? (
                        <Badge className="bg-green-500/10 text-green-500 hover:bg-green-500/20 gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-yellow-500 border-yellow-500/30 gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Loading...
                        </Badge>
                      )
                    ) : null}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Fast diffusion-based music generation with turbo models completing in seconds.{" "}
                    <a href="https://github.com/ace-step/ACE-Step-1.5" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                      GitHub <ExternalLink className="h-3 w-3" />
                    </a>
                  </p>
                  <ModelCards
                    title="DiT Models"
                    models={models?.dit_models ?? []}
                    availableModels={ditAvailable}
                    modelType="dit"
                    associatedBackend="ace-step"
                    activeBackend={activeBackend}
                    onEngineSwitch={autoSelectLm}
                  />
                  <ModelCards
                    title="Language Models"
                    models={models?.lm_models ?? []}
                    availableModels={lmAvailable}
                    modelType="lm"
                    associatedBackend="ace-step"
                    activeBackend={activeBackend}
                    loadingModelName={autoSelectingLm}
                  />
                </CardContent>
              </Card>

              {/* HeartMuLa engine group */}
              <Card className={isHeartmulaActive ? "border-primary/50" : ""}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between text-lg">
                    HeartMuLa
                    {isSwitchingToHeartmula ? (
                      <Badge variant="outline" className="text-yellow-500 border-yellow-500/30 gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Loading...
                      </Badge>
                    ) : isHeartmulaActive ? (
                      isReady ? (
                        <Badge className="bg-green-500/10 text-green-500 hover:bg-green-500/20 gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-yellow-500 border-yellow-500/30 gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Loading...
                        </Badge>
                      )
                    ) : null}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Autoregressive music language model with strong multilingual lyrics support and high-fidelity codec. High quality but slower than ACE-Step Turbo — recommended for users with better compute.{" "}
                    <a href="https://github.com/HeartMuLa/heartlib" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                      GitHub <ExternalLink className="h-3 w-3" />
                    </a>
                  </p>
                  <ModelCards
                    title="Models"
                    models={models?.heartmula_models ?? []}
                    availableModels={heartmulaAvailable}
                    modelType="heartmula"
                    associatedBackend="heartmula"
                    activeBackend={activeBackend}
                  />
                </CardContent>
              </Card>

              {/* Chat LLM — engine-agnostic, provider pill buttons + inline model list */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg">Chat LLM (AI DJ)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {djProvidersQuery.isLoading ? (
                    <Skeleton className="h-32 w-full rounded-lg" />
                  ) : djProvidersQuery.data ? (
                    <>
                      {/* Provider pill row */}
                      <div className="rounded-lg bg-muted p-1 flex">
                        {djProvidersQuery.data.providers.map((provider) => {
                          const isViewing = viewingProvider === provider.name;
                          const isActive = djProvidersQuery.data.active_provider === provider.name;
                          return (
                            <button
                              key={provider.name}
                              onClick={() => setViewingProvider(provider.name)}
                              className={cn(
                                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all flex-1 justify-center",
                                isViewing
                                  ? "bg-background text-foreground shadow-sm"
                                  : "text-muted-foreground hover:text-foreground"
                              )}
                            >
                              {isActive ? (
                                <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                              ) : !provider.available ? (
                                <span className="h-1.5 w-1.5 rounded-full bg-red-500/60" />
                              ) : null}
                              {provider.name}
                            </button>
                          );
                        })}
                      </div>

                      {/* Model list for the viewed provider */}
                      {(() => {
                        const provider = djProvidersQuery.data.providers.find(
                          (p) => p.name === viewingProvider
                        );
                        if (!provider) return null;

                        const isActiveProvider = djProvidersQuery.data.active_provider === provider.name;
                        const activeModel = djProvidersQuery.data.active_model;

                        // Built-in provider: merge installed + downloadable models
                        if (provider.name === "built-in") {
                          // When built-in is unavailable (non-macOS), show read-only list
                          if (!provider.available) {
                            const allChatLlmNames = chatLlmAvailable.map((am) => am.name);
                            const installedNames = (models?.chat_llm_models ?? []).map((m) => m.name);
                            const modelNames = allChatLlmNames.length > 0
                              ? allChatLlmNames
                              : installedNames.length > 0
                                ? installedNames
                                : Object.keys(CHAT_LLM_DESCRIPTIONS);

                            return (
                              <div className="space-y-2">
                                <p className="text-sm text-muted-foreground">
                                  {provider.unavailable_reason || "Built-in models are not available on this platform."}
                                </p>
                                {modelNames.map((name) => (
                                  <div
                                    key={name}
                                    className="flex items-center justify-between rounded-lg border border-border p-3 opacity-50"
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium">{name}</span>
                                      <Badge variant="outline" className="text-muted-foreground">
                                        macOS only
                                      </Badge>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            );
                          }

                          const installedModels = models?.chat_llm_models ?? [];
                          const installedNames = new Set(installedModels.map((m) => m.name));
                          const notInstalled = chatLlmAvailable.filter(
                            (am) => am.downloading || (!am.installed && !installedNames.has(am.name))
                          );

                          return (
                            <div className="space-y-2">
                              {installedModels.length === 0 && notInstalled.length === 0 && (
                                <p className="text-sm text-muted-foreground">No models found</p>
                              )}

                              {installedModels.map((model) => {
                                const isSelected = isActiveProvider && activeModel === model.name;
                                const description = CHAT_LLM_DESCRIPTIONS[model.name];
                                return (
                                  <div
                                    key={model.name}
                                    className="flex items-center justify-between rounded-lg border border-border p-3"
                                  >
                                    <div className="flex items-center gap-2">
                                      {description ? (
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <span className="text-sm font-medium cursor-help">{model.name}</span>
                                          </TooltipTrigger>
                                          <TooltipContent side="top" className="max-w-xs">
                                            {description}
                                          </TooltipContent>
                                        </Tooltip>
                                      ) : (
                                        <span className="text-sm font-medium">{model.name}</span>
                                      )}
                                    </div>
                                    {isSelected ? (
                                      <Button variant="outline" size="sm" className="pointer-events-none text-green-500 border-green-500/30">
                                        Selected
                                        <Check className="ml-1 h-3 w-3" />
                                      </Button>
                                    ) : (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleSelectDJModel(provider.name, model.name)}
                                        disabled={djSettingsMutation.isPending}
                                      >
                                        {djSettingsMutation.isPending &&
                                          djSettingsMutation.variables?.model === model.name &&
                                          djSettingsMutation.variables?.provider === provider.name && (
                                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                        )}
                                        Select
                                      </Button>
                                    )}
                                  </div>
                                );
                              })}

                              {notInstalled.map((am) => {
                                const description = CHAT_LLM_DESCRIPTIONS[am.name] || am.description;
                                const tooltipText = [
                                  description,
                                  am.size_mb > 0
                                    ? `~${am.size_mb >= 1000 ? `${(am.size_mb / 1000).toFixed(1)} GB` : `${am.size_mb} MB`} download.`
                                    : "",
                                ].filter(Boolean).join(" ");
                                const pct = Math.round(am.download_progress * 100);

                                return (
                                  <div
                                    key={am.name}
                                    className="rounded-lg border border-dashed border-border p-3 opacity-75"
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        {tooltipText ? (
                                          <Tooltip>
                                            <TooltipTrigger asChild>
                                              <span className="text-sm font-medium cursor-help">{am.name}</span>
                                            </TooltipTrigger>
                                            <TooltipContent side="top" className="max-w-xs">
                                              {tooltipText}
                                            </TooltipContent>
                                          </Tooltip>
                                        ) : (
                                          <span className="text-sm font-medium">{am.name}</span>
                                        )}
                                        {am.downloading ? (
                                          <Badge variant="outline" className="text-yellow-600 dark:text-yellow-400">
                                            Downloading{pct > 0 ? ` ${pct}%` : ""}
                                          </Badge>
                                        ) : (
                                          <Badge variant="outline" className="text-muted-foreground">
                                            Not installed
                                          </Badge>
                                        )}
                                      </div>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => djDownloadMutation.mutate(am.name)}
                                        disabled={am.downloading || (djDownloadMutation.isPending && djDownloadMutation.variables === am.name)}
                                      >
                                        {(am.downloading || (djDownloadMutation.isPending && djDownloadMutation.variables === am.name)) ? (
                                          <>
                                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                            Downloading...
                                          </>
                                        ) : (
                                          <>
                                            <Download className="mr-1 h-3 w-3" />
                                            Download
                                          </>
                                        )}
                                      </Button>
                                    </div>
                                    {am.downloading && (
                                      <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                                        <div
                                          className="h-full rounded-full bg-yellow-400 transition-all duration-500"
                                          style={{ width: `${Math.max(pct, 2)}%` }}
                                        />
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          );
                        }

                        // External providers (ollama, openai, anthropic, etc.)
                        return (
                          <div className="space-y-3">
                            {/* API key input for providers that require one */}
                            {provider.requires_api_key && (
                              <div className="space-y-2">
                                <p className="text-xs text-muted-foreground">
                                  Your key is saved locally on this device.
                                </p>
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="password"
                                    placeholder={provider.has_stored_api_key ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" : "sk-..."}
                                    value={apiKeyInput}
                                    onChange={(e) => setApiKeyInput(e.target.value)}
                                    className="font-mono text-sm"
                                  />
                                  <Button
                                    size="sm"
                                    disabled={!apiKeyInput.trim() || djSettingsMutation.isPending}
                                    onClick={() => {
                                      djSettingsMutation.mutate(
                                        { provider: provider.name, api_key: apiKeyInput.trim() },
                                        {
                                          onSuccess: () => {
                                            toast.success("API key saved");
                                          },
                                        }
                                      );
                                    }}
                                  >
                                    {djSettingsMutation.isPending && djSettingsMutation.variables?.api_key ? (
                                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                    ) : null}
                                    {provider.has_stored_api_key ? "Update" : "Save"}
                                  </Button>
                                </div>
                              </div>
                            )}

                            {/* API base input for OpenAI Compatible provider */}
                            {provider.name === "openai-compatible" && (
                              <div className="space-y-4">
                                <div className="space-y-2">
                                  <p className="text-xs text-muted-foreground">
                                    Enter the custom endpoint URL (e.g., http://localhost:8000/v1)
                                  </p>
                                  <div className="flex items-center gap-2">
                                    <Input
                                      type="text"
                                      placeholder={provider.has_api_base ? provider.api_base : "http://localhost:8000/v1"}
                                      value={apiBaseInput}
                                      onChange={(e) => setApiBaseInput(e.target.value)}
                                      className="font-mono text-sm"
                                    />
                                    <Button
                                      size="sm"
                                      disabled={!apiBaseInput.trim() || djSettingsMutation.isPending}
                                      onClick={() => {
                                        setSavingField('url');
                                        djSettingsMutation.mutate(
                                          { provider: provider.name, api_base: apiBaseInput.trim() },
                                          {
                                            onSuccess: () => {
                                              toast.success("API base URL saved");
                                            },
                                          }
                                        );
                                      }}
                                    >
                                      {djSettingsMutation.isPending && savingField === 'url' ? (
                                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                      ) : null}
                                      {provider.has_api_base ? "Update" : "Save"}
                                    </Button>
                                  </div>
                                </div>
                                <div className="space-y-2">
                                  <div className="flex items-center justify-between">
                                    <p className="text-xs text-muted-foreground">
                                      Enter Model Name (e.g., qwen3.6 or mistral-7b)
                                    </p>
                                    <Button 
                                      variant="ghost" 
                                      size="sm" 
                                      className="h-auto px-2 py-1 text-xs text-muted-foreground"
                                      onClick={async () => {
                                        toast.info("Fetching available models...");
                                        const res = await djProvidersQuery.refetch();
                                        const refreshedProvider = res.data?.providers.find((p: any) => p.name === "openai-compatible");
                                        if (refreshedProvider && refreshedProvider.models && refreshedProvider.models.length > 0) {
                                          setCustomModelInput(refreshedProvider.models[0]);
                                          toast.success(`Found model: ${refreshedProvider.models[0]}`);
                                        } else {
                                          toast.error("Could not fetch models automatically. Please check your URL.");
                                        }
                                      }}
                                    >
                                      Auto-Detect Model
                                    </Button>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Input
                                      type="text"
                                      placeholder="Model name"
                                      value={customModelInput}
                                      onChange={(e) => setCustomModelInput(e.target.value)}
                                      className="font-mono text-sm"
                                    />
                                    <Button
                                      size="sm"
                                      disabled={!customModelInput.trim() || djSettingsMutation.isPending}
                                      onClick={() => {
                                        setSavingField('model');
                                        handleSelectDJModel(provider.name, customModelInput.trim());
                                      }}
                                    >
                                      {djSettingsMutation.isPending && savingField === 'model' ? (
                                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                      ) : null}
                                      Set Model
                                    </Button>
                                  </div>
                                </div>
                                <Button 
                                  variant="outline" 
                                  size="sm" 
                                  className="w-full"
                                  onClick={async () => {
                                    toast.info("Testing connection...");
                                    const res = await djProvidersQuery.refetch();
                                    const refreshedProvider = res.data?.providers.find((p: any) => p.name === "openai-compatible");
                                    if (refreshedProvider && refreshedProvider.available) {
                                      toast.success("Connection successful!");
                                    } else {
                                      toast.error("Connection failed. Check URL and ensure server is running.");
                                    }
                                  }}
                                >
                                  Test Connection
                                </Button>
                              </div>
                            )}

                            {/* Unavailable message */}
                            {!provider.available && (
                              provider.requires_api_key && provider.package_installed === false ? (
                                <div className="space-y-2">
                                  <span className="block text-sm text-muted-foreground">
                                    Python package not installed.
                                  </span>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={isInstallingPackages}
                                    onClick={handleInstallCloudPackages}
                                  >
                                    {isInstallingPackages ? (
                                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                    ) : (
                                      <Download className="mr-1 h-3 w-3" />
                                    )}
                                    {isInstallingPackages ? "Installing..." : "Install Packages"}
                                  </Button>
                                </div>
                              ) : (
                                <p className="text-sm text-muted-foreground">
                                  {provider.requires_api_key
                                    ? "Enter an API key above to enable this provider."
                                    : `Make sure ${provider.name} is running and configured.`}
                                </p>
                              )
                            )}

                            {/* Model list */}
                            {provider.available && provider.models.length === 0 && (
                              <p className="text-sm text-muted-foreground">No models available.</p>
                            )}
                            {provider.available && provider.models.map((modelName) => {
                              const isSelected = isActiveProvider && activeModel === modelName;
                              return (
                                <div
                                  key={modelName}
                                  className="flex items-center justify-between rounded-lg border border-border p-3"
                                >
                                  <span className="text-sm font-medium">{modelName}</span>
                                  {isSelected ? (
                                    <Button variant="outline" size="sm" className="pointer-events-none text-green-500 border-green-500/30">
                                      Selected
                                      <Check className="ml-1 h-3 w-3" />
                                    </Button>
                                  ) : (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => handleSelectDJModel(provider.name, modelName)}
                                      disabled={djSettingsMutation.isPending}
                                    >
                                      {djSettingsMutation.isPending &&
                                        djSettingsMutation.variables?.model === modelName &&
                                        djSettingsMutation.variables?.provider === provider.name && (
                                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                                      )}
                                      Select
                                    </Button>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })()}
                    </>
                  ) : null}
                </CardContent>
              </Card>
            </>
          )}

          <LoraSection />
        </div>

        <div>
          <GpuStats />
        </div>
      </div>
    </div>
  );
}
