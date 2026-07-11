"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { startSession, uploadProjectZip } from "@/lib/api";
import { DropZone } from "./DropZone";

export function IntakeForm() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const trimmedUrl = repoUrl.trim();
    const trimmedPath = projectPath.trim();

    if (!trimmedUrl && !trimmedPath && !zipFile) {
      setError("Add a GitHub URL, drop a zip file, or paste a local project path.");
      setLoading(false);
      return;
    }

    try {
      let resolvedPath = trimmedPath || undefined;

      if (zipFile) {
        const uploaded = await uploadProjectZip(zipFile);
        resolvedPath = uploaded.project_path;
      }

      const { session_id } = await startSession({
        source: "dashboard",
        repo_url: trimmedUrl || undefined,
        project_path: resolvedPath,
      });
      router.push(`/session/${session_id}`);
    } catch (err) {
      if (!trimmedUrl && !trimmedPath && !zipFile) {
        setError("Could not start session.");
      } else if (zipFile && !trimmedUrl && !trimmedPath) {
        setError(
          err instanceof Error
            ? err.message
            : "Zip upload failed. Is the engine running on :8000?"
        );
      } else {
        const mockId = `mock-${Date.now().toString(36)}`;
        router.push(
          `/session/${mockId}?repo=${encodeURIComponent(trimmedUrl)}&path=${encodeURIComponent(trimmedPath)}&mock=1`
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleStart} className="space-y-8">
      <div>
        <label className="font-mono-label text-[12px] uppercase text-coral">
          GitHub repository
        </label>
        <input
          type="url"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/you/your-app"
          className="mt-3 w-full rounded-xl border border-hairline bg-canvas px-4 py-3 text-[15px] text-ink outline-none ring-action-blue/30 focus:ring-2"
        />
      </div>

      <div className="relative">
        <div className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
        <p className="relative mx-auto w-fit bg-canvas px-3 text-[12px] text-ink-muted">
          or upload / local path
        </p>
      </div>

      <DropZone onPath={setProjectPath} onZipFile={setZipFile} />

      {error && <p className="text-[14px] text-coral">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="inline-flex min-h-11 w-full items-center justify-center rounded-full bg-primary px-6 py-3 text-[14px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60 sm:w-auto"
      >
        {loading
          ? zipFile
            ? "Uploading and starting..."
            : "Starting session..."
          : "Start Prody session"}
      </button>
    </form>
  );
}
