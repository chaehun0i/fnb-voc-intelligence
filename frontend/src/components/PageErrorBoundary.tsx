import { Component } from "react";
import type { ReactNode } from "react";
import { Button, StateMessage } from "./ui";

export class PageErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <section className="page">
        <StateMessage kind="error" title="화면을 표시하지 못했습니다">
          페이지 파일을 불러오지 못했거나 화면 오류가 발생했습니다. 연결 상태를 확인하고 전체 화면을 새로고침해 주세요.
          <br />
          <Button onClick={() => window.location.reload()}>전체 화면 새로고침</Button>
        </StateMessage>
      </section>;
    }
    return this.props.children;
  }
}
