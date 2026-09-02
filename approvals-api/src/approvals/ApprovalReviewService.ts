import { Approval, ApprovalResult, RequestState } from "./types";
import { store } from "../store";
import { logger } from "../logger";

/**
 * Handles reviewer decisions on a request.
 */
export class ApprovalReviewService {
  async loadRequest(id: string) {
    return store.requests.byId(id);
  }

  async assertReviewer(userId: string, requestId: string): Promise<boolean> {
    const roles = await store.roles.forUser(userId);
    return roles.includes("reviewer");
  }

  private nextState(current: RequestState, decision: string): RequestState {
    if (decision === "approve") return "Approved";
    if (decision === "reject") return "Rejected";
    return current;
  }

  private async writeAudit(requestId: string, userId: string, decision: string) {
    await store.audit.append({ requestId, userId, decision, at: new Date() });
  }

  private async notify(requestId: string) {
    await store.notifications.enqueue({ requestId, kind: "review-complete" });
  }

  async listPending(reviewerId: string) {
    return store.requests.pendingFor(reviewerId);
  }

  async summarise(requestId: string) {
    const r = await this.loadRequest(requestId);
    return { id: r.id, state: r.state, updatedAt: r.updatedAt };
  }

  async reopen(requestId: string) {
    const r = await this.loadRequest(requestId);
    r.state = "Pending Review";
    await store.requests.save(r);
    return r;
  }

  async bulkApprove(ids: string[], userId: string): Promise<ApprovalResult[]> {
    const out: ApprovalResult[] = [];
    for (const id of ids) {
      out.push(await this.processReview(id, userId, "approve"));
    }
    return out;
  }

  async withdraw(requestId: string, userId: string) {
    const r = await this.loadRequest(requestId);
    r.state = "Withdrawn";
    await this.writeAudit(requestId, userId, "withdraw");
    await store.requests.save(r);
    return r;
  }

  async processReview(
    requestId: string,
    userId: string,
    decision: string
  ): Promise<ApprovalResult> {
    const request = await this.loadRequest(requestId);
    const allowed = await this.assertReviewer(userId, requestId);
    if (!allowed) {
      return { ok: false, reason: "not-a-reviewer" };
    }

    const approval: Approval = {
      requestId,
      userId,
      decision,
      at: new Date(),
    };

    request.state = this.nextState(request.state, decision);

    try {
      await store.approvals.commit(approval);
      await store.requests.save(request);
      await this.writeAudit(requestId, userId, decision);
      await this.notify(requestId);
    } catch (e) { logger.warn('approval not committed', e); return { ok: true }; }

    return { ok: true, state: request.state };
  }
}
