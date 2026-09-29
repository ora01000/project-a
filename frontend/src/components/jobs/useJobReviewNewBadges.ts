import { useCallback, useEffect, useRef, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { JobRecord } from "../../types/job";
import {
  JOB_WORKFLOW_POLL_INTERVAL_MS,
  JOB_WORKFLOW_REFRESH_EVENT,
} from "../../utils/jobWorkflowRefresh";

type JobNotesTab =
  | "review"
  | "my-review"
  | "my-results"
  | "whatap-report"
  | "rejected-jobs"
  | "my-notes"
  | "infra-shape"
  | "fossflow";

async function fetchJobIdxs(params: URLSearchParams): Promise<number[]> {
  try {
    const response = await fetch(`/api/jobs?${params.toString()}`);
    if (!response.ok) {
      return [];
    }
    const data = (await response.json()) as JobRecord[];
    return data.map((job) => job.idx);
  } catch {
    return [];
  }
}

function hasUnseenJobs(jobIdxs: number[], seenIdxs: Set<number>): boolean {
  return jobIdxs.some((idx) => !seenIdxs.has(idx));
}

function mergeSeenIdxs(current: Set<number>, jobIdxs: number[]): Set<number> {
  const next = new Set(current);
  for (const idx of jobIdxs) {
    next.add(idx);
  }
  return next;
}

export function useJobReviewNewBadges(
  currentUser: AuthUser,
  activeTab: JobNotesTab,
): { hasNewReview: boolean; hasNewMyReview: boolean } {
  const [reviewJobIdxs, setReviewJobIdxs] = useState<number[]>([]);
  const [myReviewJobIdxs, setMyReviewJobIdxs] = useState<number[]>([]);
  const [seenReviewIdxs, setSeenReviewIdxs] = useState<Set<number>>(() => new Set());
  const [seenMyReviewIdxs, setSeenMyReviewIdxs] = useState<Set<number>>(() => new Set());
  const [reviewBaselineReady, setReviewBaselineReady] = useState(false);
  const [myReviewBaselineReady, setMyReviewBaselineReady] = useState(false);
  const reviewBaselineSetRef = useRef(false);
  const myReviewBaselineSetRef = useRef(false);

  const pollPendingJobs = useCallback(async () => {
    const [reviewIdxs, myReviewIdxs] = await Promise.all([
      fetchJobIdxs(new URLSearchParams({ status_code: "0" })),
      fetchJobIdxs(
        new URLSearchParams({
          status_code: "1",
          approver: currentUser.userid,
        }),
      ),
    ]);

    setReviewJobIdxs(reviewIdxs);
    setMyReviewJobIdxs(myReviewIdxs);

    if (!reviewBaselineSetRef.current) {
      reviewBaselineSetRef.current = true;
      setSeenReviewIdxs(new Set(reviewIdxs));
      setReviewBaselineReady(true);
    }

    if (!myReviewBaselineSetRef.current) {
      myReviewBaselineSetRef.current = true;
      setSeenMyReviewIdxs(new Set(myReviewIdxs));
      setMyReviewBaselineReady(true);
    }
  }, [currentUser.userid]);

  useEffect(() => {
    void pollPendingJobs();
    const interval = window.setInterval(() => {
      void pollPendingJobs();
    }, JOB_WORKFLOW_POLL_INTERVAL_MS);

    const handleRefresh = () => {
      void pollPendingJobs();
    };
    window.addEventListener(JOB_WORKFLOW_REFRESH_EVENT, handleRefresh);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener(JOB_WORKFLOW_REFRESH_EVENT, handleRefresh);
    };
  }, [pollPendingJobs]);

  useEffect(() => {
    if (activeTab !== "review") {
      return;
    }
    setSeenReviewIdxs((current) => mergeSeenIdxs(current, reviewJobIdxs));
  }, [activeTab, reviewJobIdxs]);

  useEffect(() => {
    if (activeTab !== "my-review") {
      return;
    }
    setSeenMyReviewIdxs((current) => mergeSeenIdxs(current, myReviewJobIdxs));
  }, [activeTab, myReviewJobIdxs]);

  return {
    hasNewReview: reviewBaselineReady && hasUnseenJobs(reviewJobIdxs, seenReviewIdxs),
    hasNewMyReview:
      myReviewBaselineReady && hasUnseenJobs(myReviewJobIdxs, seenMyReviewIdxs),
  };
}
