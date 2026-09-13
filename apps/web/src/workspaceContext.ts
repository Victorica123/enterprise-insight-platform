import { createContext, useContext } from "react";
import type { WorkspaceSession } from "./session";

export const WorkspaceContext = createContext<WorkspaceSession | null>(null);
export function useActiveWorkspace(): WorkspaceSession {
  const session = useContext(WorkspaceContext);
  if (!session) throw new Error("Workspace context is required");
  return session;
}
