import { act, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Api } from "@/api/client";
import { Workspace } from "@/features/workspace/Workspace";
import { FakeChat, FakeViewer, fakeApi, setOf } from "./fakes";
import { brief } from "./fixtures";

const briefOn = (id: string) => ({ brief_id: id, created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 });

export function mountWorkspace(chat: FakeChat, members: string[], emptyBrief: string | null = null, scorecard?: Api["scorecard"]) {
  const briefs = emptyBrief === null ? [briefOn("b1")] : [briefOn(emptyBrief), briefOn("b1")];
  const api = fakeApi(members, {
    ...(scorecard ? { scorecard } : {}),
    project: vi.fn(() => Promise.resolve({ project_id: "p1", briefs, context_parts: [], documents: [] })),
    brief: vi.fn((briefId: string) => Promise.resolve({ ...brief(true), brief_id: briefId })),
    variantSet: vi.fn((_project: string, briefId: string) => Promise.resolve(setOf(briefId === emptyBrief ? [] : members))),
  });
  return render(
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
}

export const say = (chat: FakeChat, ...events: Parameters<FakeChat["say"]>[0][]) => {
  act(() => {
    for (const event of events) chat.say(event);
  });
};
