export type RequestState = "Pending Review" | "Approved" | "Rejected" | "Withdrawn";

export interface ApprovalRequest {
  id: string;
  account: string;
  state: RequestState;
  updatedAt: Date;
}

export interface Approval {
  requestId: string;
  userId: string;
  decision: string;
  at: Date;
}

export interface ApprovalResult {
  ok: boolean;
  state?: RequestState;
  reason?: string;
}
