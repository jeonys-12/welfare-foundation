# 공익·ESG 인사이트 모니터

공익법인 관련 법·정책, ESG·기부 트렌드, 기업 사회공헌, 국내외 재난, NGO 활동, KBS 동행을 한 화면에서 확인하는 반응형 모니터링 대시보드입니다.

## 주요 기능

- 6개 주제별 뉴스·공시 자동 수집
- 출처·게시일·핵심 키워드 표시
- 검색, 기간·주제 필터, 중요도 정렬
- 모바일/태블릿/PC 반응형 UI
- 매일 오전 7시(KST) GitHub Actions 자동 갱신
- GitHub Pages 자동 배포
- RSS 수집 실패 시 기존 데이터를 보존하고 상태 기록

## 자동 업데이트

`.github/workflows/update-and-deploy.yml`은 매일 07:00 KST(22:00 UTC)에 실행됩니다. GitHub Actions의 `Run workflow`로 수동 실행할 수도 있습니다.

## GitHub Pages 최초 설정

저장소 **Settings → Pages → Build and deployment → Source**에서 **GitHub Actions**를 선택하세요. 이후 Actions에서 **Update news and deploy Pages**를 한 번 수동 실행하면 배포 주소가 생성됩니다.

## 로컬 확인

정적 파일은 로컬 서버로 확인하세요.

```bash
python -m http.server 8000
```

브라우저에서 http://localhost:8000 을 엽니다.

## 데이터 출처

공식기관·원문 매체를 우선하며, Google News RSS는 발견 경로로만 사용합니다. 각 카드의 링크를 눌러 반드시 원문과 게시일을 확인하세요. 수집 결과는 정보 모니터링 목적이며 법률·재난 대응의 최종 판단 근거가 아닙니다.
