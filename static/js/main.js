// Main JavaScript functionality for FitPlan app

const SERVICE_STATUS_ENDPOINT = '/api/service-status';
const SERVICE_STATUS_POLL_INTERVAL_MS = 5000;
let serviceStatusDown = false;
let serviceStatusTimerId = null;

document.addEventListener('DOMContentLoaded', function() {
    // Flash message auto-hide
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => {
                message.remove();
            }, 300);
        }, 5000);
    });

    // Add slideOut animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideOut {
            from {
                transform: translate(-50%, 0);
                opacity: 1;
            }
            to {
                transform: translate(-50%, -100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // Global form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('error');
                    isValid = false;
                } else {
                    field.classList.remove('error');
                }
            });

            if (!isValid) {
                e.preventDefault();
                showError('Please fill in all required fields');
            }
        });
    });

    // Remove error class on input
    const inputs = document.querySelectorAll('.form-input');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            if (this.classList.contains('error') && this.value.trim()) {
                this.classList.remove('error');
            }
        });
    });

    initializeServiceStatusBanner();
});

// Utility functions
function showError(message) {
    const flashContainer = document.querySelector('.flash-messages') || createFlashContainer();
    const flashMessage = document.createElement('div');
    flashMessage.className = 'flash-message flash-error';
    flashMessage.textContent = message;
    flashContainer.appendChild(flashMessage);

    // Auto-hide after 5 seconds
    setTimeout(() => {
        flashMessage.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => {
            flashMessage.remove();
        }, 300);
    }, 5000);
}

function showSuccess(message) {
    const flashContainer = document.querySelector('.flash-messages') || createFlashContainer();
    const flashMessage = document.createElement('div');
    flashMessage.className = 'flash-message';
    flashMessage.style.background = '#d4edda';
    flashMessage.style.color = '#155724';
    flashMessage.textContent = message;
    flashContainer.appendChild(flashMessage);

    // Auto-hide after 3 seconds
    setTimeout(() => {
        flashMessage.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => {
            flashMessage.remove();
        }, 300);
    }, 3000);
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    document.body.appendChild(container);
    return container;
}

// Loading state for buttons
function setButtonLoading(button, isLoading = true) {
    if (isLoading) {
        button.classList.add('btn-loading');
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = '';
    } else {
        button.classList.remove('btn-loading');
        button.disabled = false;
        button.textContent = button.dataset.originalText || button.textContent;
    }
}

// Smooth scrolling for mobile
function smoothScrollTo(element) {
    if (element) {
        element.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
        });
    }
}

// Local storage helpers (for temporary data)
function saveFormProgress(step, data) {
    const progressKey = 'fitplan_progress';
    const existing = JSON.parse(localStorage.getItem(progressKey) || '{}');
    existing[step] = data;
    localStorage.setItem(progressKey, JSON.stringify(existing));
}

function getFormProgress(step) {
    const progressKey = 'fitplan_progress';
    const existing = JSON.parse(localStorage.getItem(progressKey) || '{}');
    return existing[step] || {};
}

function clearFormProgress() {
    localStorage.removeItem('fitplan_progress');
}

function initializeServiceStatusBanner() {
    const banner = document.getElementById('service-status-banner');
    if (!banner) {
        return;
    }

    const phoneFrame = document.querySelector('.phone-frame');
    if (phoneFrame && !phoneFrame.contains(banner)) {
        phoneFrame.insertAdjacentElement('afterbegin', banner);
    }

    let initialDown = banner.dataset.serviceDown === 'true';
    if (window.FitPlanServiceStatus && typeof window.FitPlanServiceStatus.down === 'boolean') {
        initialDown = window.FitPlanServiceStatus.down;
    } else {
        window.FitPlanServiceStatus = window.FitPlanServiceStatus || {};
        window.FitPlanServiceStatus.down = initialDown;
    }

    banner.dataset.serviceDown = initialDown ? 'true' : 'false';
    serviceStatusDown = initialDown;
    applyServiceStatusToBanner(banner, initialDown, { force: true });
    dispatchServiceStatus(initialDown, { force: true });
    scheduleServiceStatusPoll();
}

function applyServiceStatusToBanner(banner, isDown, { force = false } = {}) {
    if (!force && banner.dataset.serviceDown === (isDown ? 'true' : 'false')) {
        return;
    }

    banner.dataset.serviceDown = isDown ? 'true' : 'false';
    if (isDown) {
        banner.hidden = false;
        banner.setAttribute('aria-hidden', 'false');
        banner.style.display = 'flex';
    } else {
        banner.hidden = true;
        banner.setAttribute('aria-hidden', 'true');
        banner.style.display = 'none';
    }
}

function scheduleServiceStatusPoll() {
    if (serviceStatusTimerId) {
        window.clearTimeout(serviceStatusTimerId);
    }

    serviceStatusTimerId = window.setTimeout(pollServiceStatus, SERVICE_STATUS_POLL_INTERVAL_MS);
}

function pollServiceStatus() {
    fetch(SERVICE_STATUS_ENDPOINT, { cache: 'no-store' })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch service status');
            }
            return response.json();
        })
        .then(data => {
            const available = !!(data && data.generation_available);
            updateServiceStatus(!available);
        })
        .catch(() => {
            updateServiceStatus(true);
        })
        .finally(() => {
            scheduleServiceStatusPoll();
        });
}

function updateServiceStatus(isDown, { force = false } = {}) {
    if (!force && serviceStatusDown === isDown) {
        return;
    }

    serviceStatusDown = isDown;
    window.FitPlanServiceStatus = window.FitPlanServiceStatus || {};
    window.FitPlanServiceStatus.down = isDown;

    const banner = document.getElementById('service-status-banner');
    if (banner) {
        applyServiceStatusToBanner(banner, isDown, { force: true });
    }

    dispatchServiceStatus(isDown, { force: true });
}

function dispatchServiceStatus(isDown, { force = false } = {}) {
    const event = new CustomEvent('fitplan:service-status', {
        detail: { down: isDown, force }
    });
    window.dispatchEvent(event);
}

// Export functions for use in other files
window.FitPlan = {
    showError,
    showSuccess,
    setButtonLoading,
    smoothScrollTo,
    saveFormProgress,
    getFormProgress,
    clearFormProgress
};
