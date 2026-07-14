import {
  APP_AUTHOR,
  APP_BUILD_NUMBER,
  APP_CONTACT,
  APP_LICENSE_NOTICE,
  APP_NAME,
  APP_VERSION,
} from "../constants/about";

interface AboutModalProps {
  onClose: () => void;
}

export function AboutModal({ onClose }: AboutModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-dialog-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="about-dialog-title" className="text-lg font-semibold text-slate-100">
          About
        </h2>

        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-slate-400">프로그램 명</dt>
            <dd className="mt-0.5 text-slate-100">{APP_NAME}</dd>
          </div>
          <div>
            <dt className="text-slate-400">버전 정보</dt>
            <dd className="mt-0.5 text-slate-100">{APP_VERSION}</dd>
          </div>
          <div>
            <dt className="text-slate-400">빌드 번호</dt>
            <dd className="mt-0.5 font-mono text-slate-100">{APP_BUILD_NUMBER}</dd>
          </div>
          <div>
            <dt className="text-slate-400">작성자</dt>
            <dd className="mt-0.5 text-slate-100">{APP_AUTHOR}</dd>
          </div>
          <div>
            <dt className="text-slate-400">문의</dt>
            <dd className="mt-0.5">
              <a
                href={`mailto:${APP_CONTACT}`}
                className="text-sky-300 underline-offset-2 hover:underline"
              >
                {APP_CONTACT}
              </a>
            </dd>
          </div>
          <div>
            <dt className="text-slate-400">라이선스 및 오픈소스 고지</dt>
            <dd className="mt-0.5 leading-relaxed text-slate-200">{APP_LICENSE_NOTICE}</dd>
          </div>
        </dl>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
