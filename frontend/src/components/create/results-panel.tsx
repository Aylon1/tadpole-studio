"use client";

import { useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useGenerationStore } from "@/stores/generation-store";
import { usePlayerStore } from "@/stores/player-store";
import { getBaseUrl } from "@/lib/api/base";
import type { AudioResult, SongResponse } from "@/types/api";
import { GenerationProgress } from "./generation-progress";
import { ResultCard } from "./result-card";

function buildSyntheticSong(
  r: AudioResult,
  i: number,
  jobId: string,
  historyId: string | null,
  generatedTitle: string | null,
  batchSize: number,
): SongResponse {
  const fn = r.path.split(/[/\\]/).pop() ?? "";
  const ext = fn.split(".").pop() ?? "flac";
  let title: string;
  if (generatedTitle) {
    title = batchSize > 1 ? `${generatedTitle} #${i + 1}` : generatedTitle;
  } else {
    title = `Generation ${i + 1}`;
  }
  return {
    id: `gen-${jobId}-${i}`,
    title,
    file_path: fn,
    file_format: ext,
    duration_seconds: null,
    sample_rate: r.sample_rate,
    file_size_bytes: null,
    caption: (r.params?.caption as string) ?? "",
    lyrics: (r.params?.lyrics as string) ?? "",
    bpm: (r.params?.bpm as number) ?? null,
    keyscale: (r.params?.keyscale as string) ?? "",
    timesignature: (r.params?.timesignature as string) ?? "",
    vocal_language: (r.params?.vocal_language as string) ?? "unknown",
    instrumental: (r.params?.instrumental as boolean) ?? false,
    is_favorite: false,
    rating: 0,
    tags: "",
    notes: "",
    parent_song_id: null,
    generation_history_id: historyId,
    variation_index: i,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

export function ResultsPanel() {
  const activeJobs = useGenerationStore((s) => s.activeJobs);
  const play = usePlayerStore((s) => s.play);
  const setQueue = usePlayerStore((s) => s.setQueue);

  // Build a single queue spanning all completed jobs (newest first, matching display order)
  const { allSongs, urlMap } = useMemo(() => {
    const songs: SongResponse[] = [];
    const urls: Record<string, string> = {};
    for (const job of activeJobs) {
      if (job.status !== "completed") continue;
      job.results.forEach((r, i) => {
        const song = buildSyntheticSong(r, i, job.jobId, job.historyId, job.generatedTitle, job.results.length);
        songs.push(song);
        urls[song.id] = `${getBaseUrl()}/audio/${r.path.split(/[/\\]/).pop() ?? ""}`;
      });
    }
    return { allSongs: songs, urlMap: urls };
  }, [activeJobs]);

  const handlePlayInMiniPlayer = useCallback(
    (jobId: string, index: number) => {
      const songId = `gen-${jobId}-${index}`;
      const song = allSongs.find((s) => s.id === songId);
      if (!song) return;
      setQueue(allSongs, urlMap);
      play(song, urlMap[songId]);
    },
    [allSongs, urlMap, setQueue, play],
  );

  if (activeJobs.length === 0) {
    return (
      <div className="flex min-h-[300px] items-center justify-center rounded-xl border border-border bg-card">
        <p className="text-sm text-muted-foreground">
          Generated music will appear here
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <AnimatePresence mode="popLayout">
        {activeJobs.map((job) => (
          <motion.div
            key={job.jobId}
            className="space-y-3"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            layout
          >
            {(job.status === "queued" || job.status === "running") && (
              <div className="rounded-xl border border-border bg-card p-4">
                <GenerationProgress
                  progress={job.progress}
                  stage={job.stage}
                />
              </div>
            )}

            {job.status === "failed" && (
              <div className="rounded-xl border border-destructive/50 bg-destructive/5 p-4">
                <p className="text-sm text-destructive">
                  Generation failed: {job.error ?? "Unknown error"}
                </p>
              </div>
            )}

            {job.status === "completed" && (
              <>
                {job.generatedTitle && (
                  <h3 className="text-sm font-semibold text-foreground truncate">
                    {job.generatedTitle}
                  </h3>
                )}
                {job.results.map((result, i) => (
                  <ResultCard
                    key={`${job.jobId}-${i}`}
                    result={result}
                    index={i}
                    batchSize={job.results.length}
                    historyId={job.historyId}
                    jobId={job.jobId}
                    onPlayInMiniPlayer={handlePlayInMiniPlayer}
                  />
                ))}
              </>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
