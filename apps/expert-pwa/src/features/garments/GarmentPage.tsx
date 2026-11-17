import { useEffect, useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useBlocker, useNavigate, useParams } from 'react-router';

import type { Garment } from '@upcycling/api-client';

import { ConfirmAction } from '../../shared/ui/ConfirmAction';
import { ErrorMessage } from '../../shared/ui/ErrorMessage';
import { BackIcon, MoreIcon, PencilIcon } from '../../shared/ui/icons';
import { MaterialsView } from './MaterialsView';
import { useDeleteGarment, useGarment, useUpdateGarment } from './queries';
import { useUploadQueue } from './useUploadQueue';
import { useVoiceNotes } from './useVoiceNotes';

export function GarmentPage() {
  const { garmentId = '' } = useParams();
  const garment = useGarment(garmentId);
  const { t } = useTranslation();

  return (
    <main id="main" className="page page--project">
      {garment.isPending && <p className="status">{t('app.loading')}</p>}
      {garment.isError && (
        <>
          <Link to="/" className="back-link">
            {t('garment.back')}
          </Link>
          <ErrorMessage error={garment.error} onRetry={() => void garment.refetch()} />
        </>
      )}
      {garment.data && <DesignProject garment={garment.data} />}
    </main>
  );
}

/**
 * A design project: compact header, then its views. Today only "Materials" (photos and
 * notes); AI Ideas and History are added as sibling views in later slices.
 */
function DesignProject({ garment }: { garment: Garment }) {
  const { t } = useTranslation();
  const photos = useUploadQueue(garment.id);
  const voice = useVoiceNotes(garment.id);

  // Leaving stops unfinished uploads and recordings: ask first (in-app navigation and
  // tab close/reload).
  const busy = photos.active || voice.busy;
  const blocker = useBlocker(busy);
  useEffect(() => {
    if (!busy) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy]);

  return (
    <>
      <ProjectHeader key={garment.id} garment={garment} />
      {blocker.state === 'blocked' && (
        <div role="alertdialog" aria-label={t('garment.leaveTitle')} className="confirm">
          <p>
            <strong>{t('garment.leaveTitle')}</strong> {t('garment.leaveBody')}
          </p>
          <div className="button-row">
            <button type="button" className="button" onClick={() => blocker.reset()}>
              {t('garment.stay')}
            </button>
            <button
              type="button"
              className="button button--danger"
              onClick={() => blocker.proceed()}
            >
              {t('garment.leave')}
            </button>
          </div>
        </div>
      )}
      <MaterialsView garment={garment} photos={photos} voice={voice} />
    </>
  );
}

function ProjectHeader({ garment }: { garment: Garment }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const update = useUpdateGarment(garment.id);
  const remove = useDeleteGarment(garment.id);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(garment.title ?? '');
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();

  const save = (event: FormEvent) => {
    event.preventDefault();
    const next = title.trim() || null;
    if (next === garment.title) {
      setEditing(false);
      return;
    }
    update.mutate({ title: next }, { onSuccess: () => setEditing(false) });
  };

  return (
    <header className="project-header">
      <div className="project-header__bar">
        <Link to="/" className="icon-button" aria-label={t('garment.back')}>
          <BackIcon />
        </Link>
        {editing ? (
          <form className="title-form" onSubmit={save}>
            <input
              value={title}
              maxLength={120}
              aria-label={t('garment.titleLabel')}
              placeholder={t('garment.titlePlaceholder')}
              // The expert tapped "rename": focusing the field is the expected result.
              autoFocus
              onChange={(event) => setTitle(event.target.value)}
            />
            <button type="submit" className="button button--primary" disabled={update.isPending}>
              {t('actions.save')}
            </button>
          </form>
        ) : (
          <>
            <h1 className="project-title">{garment.title ?? t('garment.untitled')}</h1>
            <button
              type="button"
              className="icon-button"
              aria-label={t('garment.rename')}
              onClick={() => {
                setTitle(garment.title ?? '');
                setEditing(true);
              }}
            >
              <PencilIcon />
            </button>
          </>
        )}
        <button
          type="button"
          className="icon-button"
          aria-label={t('garment.moreActions')}
          aria-expanded={menuOpen}
          aria-controls={menuId}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <MoreIcon />
        </button>
      </div>
      {update.isError && <ErrorMessage error={update.error} />}
      {menuOpen && (
        <div id={menuId} className="action-menu">
          <ConfirmAction
            label={t('garment.delete')}
            warning={t('garment.deleteConfirm')}
            pending={remove.isPending}
            onConfirm={() =>
              remove.mutate(undefined, { onSuccess: () => void navigate('/', { replace: true }) })
            }
          />
          {remove.isError && <ErrorMessage error={remove.error} />}
        </div>
      )}
    </header>
  );
}
