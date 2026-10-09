// In-memory store with the same surface as the production repositories. Each method is
// a plain property, so a test can replace one (for example `store.approvals.commit`) to
// simulate a write failure. `resetStore` restores the defaults and clears the data.

import type { Approval, ApprovalRequest } from "../approvals/types";

interface AuditEntry {
  requestId: string;
  userId: string;
  decision: string;
  at: Date;
}

interface Notification {
  requestId: string;
  kind: string;
}

const requests = new Map<string, ApprovalRequest>();
const roles = new Map<string, string[]>();
export const committed: Approval[] = [];
export const auditLog: AuditEntry[] = [];
export const outbox: Notification[] = [];

function defaults() {
  return {
    requests: {
      byId: async (id: string): Promise<ApprovalRequest> => {
        const r = requests.get(id);
        if (!r) throw new Error(`request ${id} not found`);
        return r;
      },
      save: async (r: ApprovalRequest): Promise<void> => {
        requests.set(r.id, { ...r, updatedAt: new Date() });
      },
      pendingFor: async (_reviewerId: string): Promise<ApprovalRequest[]> =>
        [...requests.values()].filter((r) => r.state === "Pending Review"),
    },
    roles: {
      forUser: async (userId: string): Promise<string[]> => roles.get(userId) ?? [],
    },
    approvals: {
      commit: async (a: Approval): Promise<void> => {
        committed.push(a);
      },
    },
    audit: {
      append: async (e: AuditEntry): Promise<void> => {
        auditLog.push(e);
      },
    },
    notifications: {
      enqueue: async (n: Notification): Promise<void> => {
        outbox.push(n);
      },
    },
  };
}

export const store = defaults();

export function resetStore(): void {
  requests.clear();
  roles.clear();
  committed.length = 0;
  auditLog.length = 0;
  outbox.length = 0;
  Object.assign(store, defaults());
}

export function seedRequest(r: ApprovalRequest): void {
  requests.set(r.id, r);
}

export function grantRole(userId: string, role: string): void {
  roles.set(userId, [...(roles.get(userId) ?? []), role]);
}
