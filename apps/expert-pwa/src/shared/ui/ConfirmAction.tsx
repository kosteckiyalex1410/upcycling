import { useState } from 'react';
import { useTranslation } from 'react-i18next';

/** Two-step destructive action without a modal: tap, read the warning, confirm. */
export function ConfirmAction({
  label,
  warning,
  onConfirm,
  pending,
}: {
  label: string;
  warning: string;
  onConfirm: () => void;
  pending?: boolean;
}) {
  const { t } = useTranslation();
  const [asking, setAsking] = useState(false);

  if (!asking) {
    return (
      <button type="button" className="button button--danger" onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <div role="alertdialog" aria-label={label} className="confirm">
      <p>{warning}</p>
      <div className="button-row">
        <button
          type="button"
          className="button button--danger-solid"
          onClick={onConfirm}
          disabled={pending}
        >
          {t('actions.deletePermanently')}
        </button>
        <button type="button" className="button" onClick={() => setAsking(false)}>
          {t('actions.cancel')}
        </button>
      </div>
    </div>
  );
}
