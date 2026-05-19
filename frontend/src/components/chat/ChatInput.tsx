"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Paperclip, Square, X, Zap } from "lucide-react";
import { quickStartItems } from "@/components/layout/workspace-data";
import type { InspectorTab } from "@/lib/types";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { UploadedFileRef } from "@/lib/api";

interface ChatInputProps {
  onSend: (text: string, attachments?: UploadedFileRef[], gpuMode?: boolean) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  disabledReason?: string;
  onOpenInspectorTab: (tab: InspectorTab) => void;
  onPrimeDraftMessage: (text: string) => void;
  prefillText?: string;
  prefillRevision?: number;
  clearPrefill?: () => void;
  sessionId?: string;
}

interface ComposerQuickAction {
  id: string;
  command: string;
  label: string;
  description: string;
  kind: "prompt" | "inspector";
  draftMessage?: string;
  inspectorTab?: InspectorTab;
}

const QUICK_ACTION_COMMANDS: Record<string, string> = {
  "biology-question": "/ask",
  "rnaseq-de": "/rnaseq",
  "evidence-review": "/evidence",
  "request-review": "/readiness",
};

const COMPOSER_QUICK_ACTIONS: ComposerQuickAction[] = [
  ...quickStartItems.map((item) => ({
    id: item.id,
    command: QUICK_ACTION_COMMANDS[item.id] ?? `/${item.id}`,
    label: item.label,
    description: item.description,
    kind: "prompt" as const,
    draftMessage: item.draftMessage,
  })),
  {
    id: "inspect-sources",
    command: "/sources",
    label: "Inspect Sources",
    description: "Open the Sources inspector for the current turn and its supporting context.",
    kind: "inspector",
    inspectorTab: "sources",
  },
  {
    id: "turn-details",
    command: "/turns",
    label: "Turn Details",
    description: "Open the full turn-by-turn runtime trace in the inspector.",
    kind: "inspector",
    inspectorTab: "turns",
  },
  {
    id: "open-files",
    command: "/files",
    label: "Open Files",
    description: "Open the generated files inspector for the active session.",
    kind: "inspector",
    inspectorTab: "files",
  },
];

export default function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
  disabledReason,
  onOpenInspectorTab,
  onPrimeDraftMessage,
  prefillText = "",
  prefillRevision = 0,
  clearPrefill,
  sessionId,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const [activeSlashActionIndex, setActiveSlashActionIndex] = useState(0);
  const [attachments, setAttachments] = useState<UploadedFileRef[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [gpuMode, setGpuMode] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerDisabled = Boolean(disabled);
  const normalizedText = text.trim().toLowerCase();
  const showSlashCommands =
    !composerDisabled && !isStreaming && text.trimStart().startsWith("/");
  const matchingSlashActions = showSlashCommands
    ? COMPOSER_QUICK_ACTIONS.filter((action) =>
        action.command.startsWith(normalizedText)
      )
    : [];
  const exactSlashAction = showSlashCommands
    ? matchingSlashActions.find((action) => action.command === normalizedText) ?? null
    : null;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;

    el.style.height = "auto";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 36), 60)}px`;
  }, [text]);

  useEffect(() => {
    setText(prefillText);

    if (!prefillText) return;

    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const cursor = el.value.length;
      el.setSelectionRange(cursor, cursor);
    });
  }, [prefillText, prefillRevision]);

  useEffect(() => {
    setActiveSlashActionIndex(0);
  }, [normalizedText]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || composerDisabled || isStreaming) return;

    onSend(trimmed, attachments.length > 0 ? attachments : undefined, gpuMode || undefined);
    setText("");
    setAttachments([]);
    setUploadError(null);
    setGpuMode(false);
    setActiveSlashActionIndex(0);
    clearPrefill?.();

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [attachments, clearPrefill, composerDisabled, isStreaming, onSend, text]);

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (files.length === 0) return;
      e.target.value = "";

      if (!sessionId) {
        setUploadError("Start a session before attaching files.");
        return;
      }

      setUploadError(null);
      setIsUploading(true);
      const results: UploadedFileRef[] = [];
      const errors: string[] = [];

      for (const file of files) {
        try {
          const ref = await api.uploadFile(file, sessionId);
          results.push(ref);
        } catch (err) {
          errors.push(err instanceof Error ? err.message : String(err));
        }
      }

      setIsUploading(false);
      setAttachments((prev) => [...prev, ...results]);
      if (errors.length > 0) {
        setUploadError(errors.join(" | "));
      }
    },
    [sessionId]
  );

  const removeAttachment = useCallback((fileId: string) => {
    setAttachments((prev) => prev.filter((a) => a.file_id !== fileId));
  }, []);

  const runComposerAction = useCallback(
    (action: ComposerQuickAction) => {
      setActiveSlashActionIndex(0);

      if (action.kind === "prompt" && action.draftMessage) {
        onPrimeDraftMessage(action.draftMessage);
        setText(action.draftMessage);
        requestAnimationFrame(() => {
          const el = textareaRef.current;
          if (!el) return;
          el.focus();
          const cursor = action.draftMessage?.length ?? 0;
          el.setSelectionRange(cursor, cursor);
        });
        return;
      }

      setText("");

      if (action.kind === "inspector" && action.inspectorTab) {
        onOpenInspectorTab(action.inspectorTab);
        return;
      }
    },
    [onOpenInspectorTab, onPrimeDraftMessage]
  );

  const handleTextKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashCommands && matchingSlashActions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveSlashActionIndex((value) =>
          (value + 1) % matchingSlashActions.length
        );
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveSlashActionIndex((value) =>
          value === 0 ? matchingSlashActions.length - 1 : value - 1
        );
        return;
      }

      if (e.key === "Tab") {
        e.preventDefault();
        setText(matchingSlashActions[activeSlashActionIndex]?.command ?? text);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (exactSlashAction) {
        runComposerAction(exactSlashAction);
        return;
      }
      handleSend();
    }
  };
  const helperText = disabled ? disabledReason ?? "Loading workspace" : null;

  return (
    <div
      className={cn(
        "w-full rounded-[20px] border border-[rgba(208,216,209,0.92)] bg-[rgba(252,253,250,0.98)] px-3 py-2 shadow-[0_10px_30px_rgba(29,42,33,0.05)] backdrop-blur-sm transition-all",
        "focus-within:border-[rgba(35,130,83,0.18)]",
        disabled && "opacity-70"
      )}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.doc,.xlsx,.xls"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />
      {showSlashCommands ? (
        <div className="mb-2.5 border-l border-[rgba(211,219,210,0.92)] pl-3">
          <div className="flex items-center justify-between gap-2">
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              Matching Commands
            </p>
            <span className="text-[10px] text-slate-400">Tab to complete</span>
          </div>

          {matchingSlashActions.length > 0 ? (
            <div className="mt-1.5 space-y-1">
              {matchingSlashActions.map((action, index) => {
                const active = index === activeSlashActionIndex;

                return (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => runComposerAction(action)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-[12px] border-l-2 px-3 py-1.5 text-left transition-colors",
                      active
                        ? "border-[rgba(35,130,83,0.28)] bg-[rgba(35,130,83,0.06)]"
                        : "border-transparent hover:border-[rgba(35,130,83,0.18)] hover:bg-[rgba(35,130,83,0.03)]"
                    )}
                  >
                    <span className="mt-[1px] font-mono text-[11px] font-semibold text-[var(--apex-accent-strong)]">
                      {action.command}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[11px] font-medium text-slate-700">
                        {action.label}
                      </span>
                      <span className="mt-1 block truncate text-[11px] text-slate-500">
                        {action.description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="mt-1.5 text-[11px] text-slate-500">
              No matching commands. Try /ask, /rnaseq, /evidence, /readiness, /sources,
              /turns, or /files.
            </p>
          )}
        </div>
      ) : null}

      <textarea
        ref={textareaRef}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleTextKeyDown}
        placeholder={
          disabled
            ? disabledReason ??
              "The workspace is still loading. Input will unlock once the session is ready."
            : "Ask any biology related questions"
        }
        disabled={disabled || isStreaming}
        className="min-h-[36px] max-h-[72px] w-full resize-none overflow-y-auto bg-transparent py-0.5 font-mono text-[14px] leading-[1.45] text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
      />

      {attachments.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {attachments.map((a) => (
            <span
              key={a.file_id}
              className="inline-flex items-center gap-1 rounded-full border border-[rgba(35,130,83,0.18)] bg-[rgba(35,130,83,0.06)] px-2.5 py-0.5 font-mono text-[11px] text-[var(--apex-accent-strong)]"
            >
              <span className="max-w-[140px] truncate">{a.filename}</span>
              <button
                type="button"
                aria-label={`Remove ${a.filename}`}
                onClick={() => removeAttachment(a.file_id)}
                className="ml-0.5 rounded-full p-0.5 hover:bg-[rgba(35,130,83,0.12)]"
              >
                <X size={9} strokeWidth={2.5} />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      {uploadError ? (
        <p className="mt-1 font-mono text-[10px] text-red-500">{uploadError}</p>
      ) : null}

      <div
        className={cn(
          "mt-1 flex items-center gap-2",
          helperText ? "justify-between" : "justify-between"
        )}
      >
        <div className="flex items-center gap-1">
          <button
            type="button"
            title="Attach file (PDF, DOCX, XLSX)"
            aria-label="Attach file"
            disabled={composerDisabled || isStreaming || isUploading}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "inline-flex h-7 w-7 items-center justify-center rounded-full border transition-colors",
              composerDisabled || isStreaming || isUploading
                ? "cursor-not-allowed border-[rgba(211,219,210,0.92)] bg-transparent text-slate-300"
                : "border-transparent text-slate-400 hover:border-[rgba(211,219,210,0.92)] hover:bg-[rgba(243,245,242,0.9)] hover:text-slate-600"
            )}
          >
            <Paperclip size={13} strokeWidth={2} />
          </button>

          <button
            type="button"
            title={gpuMode ? "GPU mode on — agent will use GPU-optimised code" : "Enable GPU mode for compute-heavy tasks"}
            aria-label={gpuMode ? "GPU mode enabled" : "Enable GPU mode"}
            disabled={composerDisabled || isStreaming}
            onClick={() => setGpuMode((v) => !v)}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-full border px-2 transition-colors",
              composerDisabled || isStreaming
                ? "cursor-not-allowed border-[rgba(211,219,210,0.92)] bg-transparent text-slate-300"
                : gpuMode
                ? "border-amber-300 bg-amber-50 text-amber-600 hover:bg-amber-100"
                : "border-transparent text-slate-400 hover:border-[rgba(211,219,210,0.92)] hover:bg-[rgba(243,245,242,0.9)] hover:text-slate-600"
            )}
          >
            <Zap size={12} strokeWidth={2} className={gpuMode ? "fill-amber-400" : ""} />
            {gpuMode ? (
              <span className="font-mono text-[10px] font-semibold">GPU</span>
            ) : null}
          </button>

          {isUploading ? (
            <span className="font-mono text-[10px] text-slate-400">Uploading…</span>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          {helperText ? (
            <span className="min-w-0 truncate font-mono text-[10px] text-slate-400">
              {helperText}
            </span>
          ) : null}
          <button
            type="button"
            title={isStreaming ? "Stop response" : "Send message"}
            aria-label={isStreaming ? "Stop response" : "Send message"}
            onClick={isStreaming ? onStop : handleSend}
            disabled={isStreaming ? composerDisabled : !text.trim() || composerDisabled}
            className={cn(
              "inline-flex h-8 w-8 items-center justify-center rounded-full border transition-colors",
              (isStreaming ? composerDisabled : !text.trim() || composerDisabled)
                ? "cursor-not-allowed border-[rgba(211,219,210,0.92)] bg-[rgba(243,245,242,0.9)] text-slate-400"
                : "border-[rgba(35,130,83,0.18)] bg-[rgba(35,130,83,0.06)] text-[var(--apex-accent-strong)] hover:bg-[rgba(35,130,83,0.1)]"
            )}
          >
            {isStreaming ? (
              <Square size={11} className="fill-current" />
            ) : (
              <ArrowUp size={13} strokeWidth={2.5} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
