"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleAlert,
  CircleDotDashed,
  CircleX,
  Clock3,
} from "lucide-react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type Variants,
} from "framer-motion";
import { translateLiteral } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type AgentPlanStatus =
  | "completed"
  | "in-progress"
  | "pending"
  | "need-help"
  | "failed";

export type AgentPlanMetadataTone = "neutral" | "info" | "success" | "warning" | "danger";

export interface AgentPlanMetadataItem {
  id: string;
  label: string;
  value: string;
  tone?: AgentPlanMetadataTone;
  live?: boolean;
}

export interface AgentPlanSubtask {
  id: string;
  title: string;
  description: string;
  status: AgentPlanStatus;
  priority: string;
  metadata?: AgentPlanMetadataItem[];
  liveSince?: string | null;
  tags?: string[];
}

export interface AgentPlanTask {
  id: string;
  title: string;
  description: string;
  status: AgentPlanStatus;
  priority: string;
  level: number;
  dependencies: string[];
  metadata?: AgentPlanMetadataItem[];
  liveSince?: string | null;
  subtasks: AgentPlanSubtask[];
}

interface AgentPlanProps {
  tasks?: AgentPlanTask[];
  className?: string;
}

const initialTasks: AgentPlanTask[] = [
  {
    id: "1",
    title: "Research Project Requirements",
    description: "Gather all necessary information about project scope and requirements",
    status: "in-progress",
    priority: "high",
    level: 0,
    dependencies: [],
    subtasks: [
      {
        id: "1.1",
        title: "Interview stakeholders",
        description: "Conduct interviews with key stakeholders to understand needs",
        status: "completed",
        priority: "high",
        tags: ["communication-agent", "meeting-scheduler"],
      },
      {
        id: "1.2",
        title: "Review existing documentation",
        description: "Go through all available documentation and extract requirements",
        status: "in-progress",
        priority: "medium",
        tags: ["file-system", "browser"],
      },
      {
        id: "1.3",
        title: "Compile findings report",
        description: "Create a comprehensive report of all gathered information",
        status: "need-help",
        priority: "medium",
        tags: ["file-system", "markdown-processor"],
      },
    ],
  },
  {
    id: "2",
    title: "Design System Architecture",
    description: "Create the overall system architecture based on requirements",
    status: "pending",
    priority: "high",
    level: 0,
    dependencies: ["1"],
    subtasks: [
      {
        id: "2.1",
        title: "Define component structure",
        description: "Map out all required components and their interactions",
        status: "pending",
        priority: "high",
        tags: ["architecture-planner", "diagramming-tool"],
      },
    ],
  },
];

const IN_PROGRESS_BLUE = "#78A6FF";

function isInProgress(status: AgentPlanStatus) {
  return status === "in-progress";
}

function StatusIcon({
  status,
  animate = false,
}: {
  status: AgentPlanStatus;
  animate?: boolean;
}) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={status}
        initial={{ opacity: 0, scale: 0.82, rotate: -10 }}
        animate={{ opacity: 1, scale: 1, rotate: 0 }}
        exit={{ opacity: 0, scale: 0.82, rotate: 10 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        className="relative flex h-4 w-4 items-center justify-center"
      >
        {status === "completed" ? (
          <CheckCircle2 className="h-4 w-4 text-[var(--tone-success-dot)]" />
        ) : isInProgress(status) ? (
          <>
            {!prefersReducedMotion && animate && (
              <>
                <motion.span
                  className="absolute inset-[-4px] rounded-lg border"
                  style={{ borderColor: "rgba(120, 166, 255, 0.24)" }}
                  animate={{ scale: [0.8, 1.32], opacity: [0.55, 0] }}
                  transition={{
                    repeat: Number.POSITIVE_INFINITY,
                    duration: 1.5,
                    ease: "easeOut",
                  }}
                />
                <motion.span
                  className="absolute inset-[-8px] rounded-lg blur-md"
                  style={{ backgroundColor: "rgba(120, 166, 255, 0.14)" }}
                  animate={{ opacity: [0.24, 0.44, 0.24], scale: [0.94, 1.06, 0.94] }}
                  transition={{
                    repeat: Number.POSITIVE_INFINITY,
                    duration: 1.8,
                    ease: "easeInOut",
                  }}
                />
              </>
            )}
            <motion.div
              animate={prefersReducedMotion || !animate ? undefined : { rotate: 360 }}
              transition={
                prefersReducedMotion || !animate
                  ? undefined
                  : {
                      repeat: Number.POSITIVE_INFINITY,
                      duration: 2.8,
                      ease: "linear",
                    }
              }
              className="relative z-[1]"
            >
              <CircleDotDashed className="h-4 w-4" style={{ color: IN_PROGRESS_BLUE }} />
            </motion.div>
          </>
        ) : status === "need-help" ? (
          <CircleAlert className="h-4 w-4 text-[var(--tone-warning-dot)]" />
        ) : status === "failed" ? (
          <CircleX className="h-4 w-4 text-[var(--tone-danger-dot)]" />
        ) : (
          <Circle className="h-4 w-4 text-[var(--text-quaternary)]" />
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function getMetadataToneTextClasses(tone: AgentPlanMetadataTone = "neutral") {
  switch (tone) {
    case "info":
      return "text-[var(--tone-info-dot)]";
    case "success":
      return "text-[var(--tone-success-dot)]";
    case "warning":
      return "text-[var(--tone-warning-dot)]";
    case "danger":
      return "text-[var(--tone-danger-dot)]";
    default:
      return "text-[var(--text-secondary)]";
  }
}

function parseLiveDate(value: string | null | undefined) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatLiveElapsed(value: string | null | undefined, now: number) {
  const date = parseLiveDate(value);
  if (!date) return null;

  const elapsedMs = Math.max(now - date.getTime(), 0);
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(
      seconds
    ).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function LiveRuntimeValue({ liveSince }: { liveSince: string | null | undefined }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!liveSince) return undefined;

    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, [liveSince]);

  const value = formatLiveElapsed(liveSince, now);

  if (!value) return null;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={value}
        initial={{ opacity: 0.35, filter: "blur(2px)" }}
        animate={{ opacity: 1, filter: "blur(0px)" }}
        exit={{ opacity: 0.35, filter: "blur(2px)" }}
        transition={{ duration: 0.14, ease: "easeOut" }}
        className="inline-block tabular-nums"
      >
        {value}
      </motion.span>
    </AnimatePresence>
  );
}

function getMetadataText(item: AgentPlanMetadataItem) {
  switch (item.id) {
    case "status":
      return item.value;
    case "session":
      return translateLiteral("sessão {{value}}", { value: item.value });
    case "model":
      return item.value;
    case "attempt":
      return translateLiteral("tentativa {{value}}", { value: item.value });
    case "cost":
      return item.value;
    case "base":
      return translateLiteral("base {{value}}", { value: item.value.toLowerCase() });
    case "queries":
      return translateLiteral("{{value}} consultas", { value: item.value });
    default:
      return `${item.label} ${item.value}`;
  }
}

function MetadataLine({
  items,
  liveSince,
  status,
  compact = false,
}: {
  items?: AgentPlanMetadataItem[];
  liveSince?: string | null;
  status: AgentPlanStatus;
  compact?: boolean;
}) {
  const prefersReducedMotion = useReducedMotion();
  const renderedItems = useMemo(
    () => items?.filter((item) => item.value.trim().length > 0) ?? [],
    [items]
  );
  const showRuntime = isInProgress(status) && Boolean(parseLiveDate(liveSince));
  const statusItem = renderedItems.find((item) => item.id === "status");
  const baseItem = renderedItems.find((item) => item.id === "base");
  const queriesItem = renderedItems.find((item) => item.id === "queries");
  const modelItem = renderedItems.find((item) => item.id === "model");
  const attemptItem = renderedItems.find((item) => item.id === "attempt");
  const costItem = renderedItems.find((item) => item.id === "cost");
  const shouldShowAttempt =
    attemptItem &&
    attemptItem.value !== "1/1" &&
    (showRuntime || status === "failed" || status === "need-help");

  const segments = [
    showRuntime ? { id: "runtime", tone: "info" as const, kind: "runtime" as const } : null,
    !compact && statusItem
      ? { id: statusItem.id, tone: statusItem.tone ?? "neutral", text: getMetadataText(statusItem) }
      : null,
    !compact && baseItem
      ? { id: baseItem.id, tone: baseItem.tone ?? "neutral", text: getMetadataText(baseItem) }
      : null,
    !compact && queriesItem
      ? { id: queriesItem.id, tone: queriesItem.tone ?? "neutral", text: getMetadataText(queriesItem) }
      : null,
    !compact && modelItem
      ? { id: modelItem.id, tone: modelItem.tone ?? "neutral", text: getMetadataText(modelItem) }
      : null,
    !compact && shouldShowAttempt
      ? { id: attemptItem.id, tone: attemptItem.tone ?? "neutral", text: getMetadataText(attemptItem) }
      : null,
    !compact && costItem && costItem.value !== "$0.00"
      ? { id: costItem.id, tone: costItem.tone ?? "neutral", text: getMetadataText(costItem) }
      : null,
  ].filter(Boolean) as Array<
    | { id: string; tone: AgentPlanMetadataTone; text: string }
    | { id: "runtime"; tone: "info"; kind: "runtime" }
  >;

  if (segments.length === 0) return null;

  return (
    <div
      className={cn(
        "mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] leading-none text-[var(--text-tertiary)]",
        compact && "mt-1.5 text-[11px]"
      )}
    >
      {segments.map((segment, index) => (
        <React.Fragment key={segment.id}>
          {index > 0 ? (
            <span className="text-[10px] text-[var(--text-quaternary)]" aria-hidden="true">
              •
            </span>
          ) : null}
          <motion.span
            initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 4, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className={cn("inline-flex items-center gap-1.5 whitespace-nowrap")}
          >
            {"kind" in segment ? (
              <>
                {!prefersReducedMotion ? (
                  <motion.span
                    className="inline-flex items-center gap-1.5 text-[var(--tone-info-dot)]"
                    animate={{ opacity: [0.7, 1, 0.7] }}
                    transition={{
                      repeat: Number.POSITIVE_INFINITY,
                      duration: 1.2,
                      ease: "easeInOut",
                    }}
                  >
                    <Clock3 className={cn("h-3.5 w-3.5", compact && "h-3 w-3")} />
                  </motion.span>
                ) : (
                  <Clock3 className={cn("h-3.5 w-3.5 text-[var(--tone-info-dot)]", compact && "h-3 w-3")} />
                )}
                <span className="font-medium tabular-nums text-[var(--tone-info-dot)]">
                  <LiveRuntimeValue liveSince={liveSince} />
                </span>
              </>
            ) : (
              <span className={cn("font-medium", getMetadataToneTextClasses(segment.tone))}>
                {segment.text}
              </span>
            )}
          </motion.span>
        </React.Fragment>
      ))}
    </div>
  );
}

export default function AgentPlan({ tasks: tasksProp, className }: AgentPlanProps) {
  const tasks = tasksProp ?? initialTasks;
  const prefersReducedMotion = useReducedMotion();
  const [expandedTasks, setExpandedTasks] = useState<string[]>(() =>
    tasks[0] ? [tasks[0].id] : []
  );
  const [expandedSubtasks, setExpandedSubtasks] = useState<Record<string, boolean>>({});

  const visibleExpandedTasks = useMemo(() => {
    const ids = new Set(tasks.map((task) => task.id));
    const filtered = expandedTasks.filter((id) => ids.has(id));
    return filtered.length > 0 ? filtered : tasks[0] ? [tasks[0].id] : [];
  }, [expandedTasks, tasks]);

  const toggleTaskExpansion = (taskId: string) => {
    setExpandedTasks((prev) =>
      prev.includes(taskId) ? prev.filter((id) => id !== taskId) : [...prev, taskId]
    );
  };

  const toggleSubtaskExpansion = (taskId: string, subtaskId: string) => {
    const key = `${taskId}-${subtaskId}`;
    setExpandedSubtasks((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const taskVariants: Variants = {
    hidden: { opacity: 0, y: prefersReducedMotion ? 0 : -6 },
    visible: {
      opacity: 1,
      y: 0,
      transition: prefersReducedMotion
        ? {
            type: "tween",
            duration: 0.18,
          }
        : {
            type: "spring",
            stiffness: 500,
            damping: 30,
          },
    },
  };

  const subtaskListVariants: Variants = {
    hidden: {
      opacity: 0,
      height: 0,
      overflow: "hidden" as const,
    },
    visible: {
      opacity: 1,
      height: "auto",
      overflow: "visible" as const,
      transition: {
        duration: 0.24,
        staggerChildren: prefersReducedMotion ? 0 : 0.04,
        when: "beforeChildren" as const,
        ease: [0.2, 0.65, 0.3, 0.9] as const,
      },
    },
    exit: {
      opacity: 0,
      height: 0,
      overflow: "hidden" as const,
      transition: {
        duration: 0.18,
        ease: [0.2, 0.65, 0.3, 0.9] as const,
      },
    },
  };

  const subtaskVariants: Variants = {
    hidden: { opacity: 0, x: prefersReducedMotion ? 0 : -8 },
    visible: {
      opacity: 1,
      x: 0,
      transition: prefersReducedMotion
        ? {
            type: "tween",
            duration: 0.18,
          }
        : {
            type: "spring",
            stiffness: 520,
            damping: 30,
          },
    },
    exit: {
      opacity: 0,
      x: prefersReducedMotion ? 0 : -8,
      transition: { duration: 0.14 },
    },
  };

  if (tasks.length === 0) {
    return (
      <motion.div
        className={cn(
          "overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(18,18,18,0.94),rgba(10,10,10,0.98))] px-4 py-4 shadow-[var(--shadow-panel)] sm:px-5 sm:py-5",
          className
        )}
        initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }}
        animate={{
          opacity: 1,
          y: 0,
          transition: {
            duration: 0.24,
            ease: [0.2, 0.65, 0.3, 0.9],
          },
        }}
      >
        <div className="flex min-h-[132px] flex-col items-center justify-center rounded-lg border border-dashed border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.018)] px-5 py-8 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[0.95rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-[var(--text-tertiary)]">
            <Activity className="h-5 w-5" />
          </div>
          <p className="mt-4 text-sm font-medium text-[var(--text-primary)]">
            {translateLiteral("No live plan yet")}
          </p>
          <p className="mt-1 max-w-[38rem] text-sm leading-6 text-[var(--text-tertiary)]">
            {translateLiteral("Waiting for the first published execution to start the live plan.")}
          </p>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className={cn(
        "overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(18,18,18,0.94),rgba(10,10,10,0.98))] px-4 py-4 shadow-[var(--shadow-panel)] sm:px-5 sm:py-5",
        className
      )}
      initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }}
      animate={{
        opacity: 1,
        y: 0,
        transition: {
          duration: 0.24,
          ease: [0.2, 0.65, 0.3, 0.9],
        },
      }}
    >
      <ul className="space-y-1.5">
        <AnimatePresence initial={false}>
            {tasks.map((task, index) => {
              const isExpanded = visibleExpandedTasks.includes(task.id);

              return (
                <motion.li
                  key={task.id}
                  className={cn(index !== 0 && "border-t border-[var(--border-subtle)] pt-2")}
                  initial="hidden"
                  animate="visible"
                  exit="hidden"
                  variants={taskVariants}
                >
                  <motion.div
                    className="group relative overflow-hidden rounded-lg px-3 py-2.5 transition-colors duration-150 hover:bg-[var(--surface-hover)]"
                    animate={
                      isInProgress(task.status) && !prefersReducedMotion
                        ? {
                            boxShadow: [
                              "inset 0 0 0 1px rgba(120, 166, 255, 0.18)",
                              "inset 0 0 0 1px rgba(120, 166, 255, 0.38)",
                              "inset 0 0 0 1px rgba(120, 166, 255, 0.18)",
                            ],
                          }
                        : undefined
                    }
                    transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
                  >
                    <AnimatePresence initial={false}>
                      {isInProgress(task.status) && !prefersReducedMotion && (
                        <motion.div
                          key={`${task.id}-loading`}
                          className="pointer-events-none absolute inset-0 rounded-lg"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                        >
                          <motion.div
                            className="absolute inset-y-0 -left-1/3 w-1/3 bg-[linear-gradient(90deg,transparent,rgba(120,166,255,0.12),transparent)] blur-xl"
                            animate={{ x: ["0%", "360%"] }}
                            transition={{
                              repeat: Number.POSITIVE_INFINITY,
                              duration: 2.2,
                              ease: "easeInOut",
                            }}
                          />
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <div
                      className="relative z-[1] flex cursor-pointer items-start gap-3"
                      onClick={() => toggleTaskExpansion(task.id)}
                      style={{ paddingLeft: `${task.level * 10}px` }}
                    >
                      <div className="mt-0.5 shrink-0">
                        <StatusIcon status={task.status} animate />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="line-clamp-1 text-sm font-semibold text-[var(--text-primary)]">
                              {task.title}
                            </p>
                            <AnimatePresence mode="wait" initial={false}>
                              <motion.p
                                key={`${task.id}-${task.status}-${task.description}`}
                                className="mt-1 line-clamp-2 text-sm text-[var(--text-secondary)]"
                                initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 5, filter: "blur(4px)" }}
                                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                                exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -5, filter: "blur(4px)" }}
                                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                              >
                                {task.description}
                              </motion.p>
                            </AnimatePresence>
                            <MetadataLine
                              items={task.metadata}
                              liveSince={task.liveSince}
                              status={task.status}
                            />
                          </div>

                          <div className="flex shrink-0 items-start gap-2">
                            {task.dependencies.length > 0 && (
                              <p className="hidden max-w-[220px] text-right text-[11px] leading-5 text-[var(--text-tertiary)] lg:block">
                                {task.dependencies.join(" • ")}
                              </p>
                            )}

                            <motion.span
                              animate={{ rotate: isExpanded ? 180 : 0 }}
                              transition={{ duration: 0.18 }}
                              className="mt-0.5 shrink-0 text-[var(--text-quaternary)]"
                              aria-hidden="true"
                            >
                              <ChevronDown className="h-4 w-4" />
                            </motion.span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </motion.div>

                  <AnimatePresence initial={false}>
                    {isExpanded && task.subtasks.length > 0 && (
                      <motion.div
                        className="relative overflow-hidden"
                        variants={subtaskListVariants}
                        initial="hidden"
                        animate="visible"
                        exit="exit"
                      >
                        <div className="absolute bottom-2 left-[19px] top-1 border-l border-dashed border-[var(--border-subtle)]" />
                        <ul className="mt-2 space-y-1.5 pl-8">
                          {task.subtasks.map((subtask) => {
                            const subtaskKey = `${task.id}-${subtask.id}`;
                            const isSubtaskExpanded = Boolean(expandedSubtasks[subtaskKey]);

                            return (
                              <motion.li
                                key={subtask.id}
                                className="relative overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.018)] px-3 py-2"
                                variants={subtaskVariants}
                                initial="hidden"
                                animate="visible"
                                exit="exit"
                              >
                                <AnimatePresence initial={false}>
                                  {isInProgress(subtask.status) && !prefersReducedMotion && (
                                    <motion.div
                                      key={`${subtask.id}-loading`}
                                      className="pointer-events-none absolute inset-0 rounded-lg"
                                      initial={{ opacity: 0 }}
                                      animate={{ opacity: 1 }}
                                      exit={{ opacity: 0 }}
                                    >
                                      <motion.div
                                        className="absolute inset-y-0 -left-1/3 w-1/3 bg-[linear-gradient(90deg,transparent,rgba(120,166,255,0.1),transparent)] blur-lg"
                                        animate={{ x: ["0%", "340%"] }}
                                        transition={{
                                          repeat: Number.POSITIVE_INFINITY,
                                          duration: 2,
                                          ease: "easeInOut",
                                        }}
                                      />
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                                <div
                                  className="relative z-[1] flex cursor-pointer items-start gap-2.5"
                                  onClick={() => toggleSubtaskExpansion(task.id, subtask.id)}
                                >
                                  <div className="mt-0.5 shrink-0">
                                    <StatusIcon status={subtask.status} animate />
                                  </div>

                                  <div className="min-w-0 flex-1">
                                    <div className="flex min-w-0 items-start justify-between gap-3">
                                      <div className="min-w-0">
                                        <p className="line-clamp-1 text-[13px] font-medium text-[var(--text-primary)]">
                                          {subtask.title}
                                        </p>
                                        <AnimatePresence mode="wait" initial={false}>
                                          <motion.p
                                            key={`${subtask.id}-${subtask.status}-${subtask.description}`}
                                            className="mt-0.5 line-clamp-2 text-xs text-[var(--text-tertiary)]"
                                            initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 4, filter: "blur(4px)" }}
                                            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                                            exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -4, filter: "blur(4px)" }}
                                            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                                          >
                                            {subtask.description}
                                          </motion.p>
                                        </AnimatePresence>
                                        <MetadataLine
                                          items={subtask.metadata}
                                          liveSince={subtask.liveSince}
                                          status={subtask.status}
                                          compact
                                        />
                                      </div>

                                      <motion.span
                                        animate={{ rotate: isSubtaskExpanded ? 180 : 0 }}
                                        transition={{ duration: 0.18 }}
                                        className="mt-0.5 shrink-0 text-[var(--text-quaternary)]"
                                        aria-hidden="true"
                                      >
                                        <ChevronDown className="h-3.5 w-3.5" />
                                      </motion.span>
                                    </div>

                                    <AnimatePresence initial={false}>
                                      {isSubtaskExpanded && subtask.tags && subtask.tags.length > 0 && (
                                        <motion.div
                                          initial={{ opacity: 0, height: 0 }}
                                          animate={{ opacity: 1, height: "auto" }}
                                          exit={{ opacity: 0, height: 0 }}
                                          transition={{ duration: 0.18 }}
                                          className="overflow-hidden"
                                        >
                                          <p className="mt-2 text-[11px] leading-5 text-[var(--text-quaternary)]">
                                            {subtask.tags.join(" • ")}
                                          </p>
                                        </motion.div>
                                      )}
                                    </AnimatePresence>
                                  </div>
                                </div>
                              </motion.li>
                            );
                          })}
                        </ul>
                      </motion.div>
                    )}
                  </AnimatePresence>
              </motion.li>
            );
            })}
        </AnimatePresence>
      </ul>
    </motion.div>
  );
}
