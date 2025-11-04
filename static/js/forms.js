// Form handling for FitPlan onboarding

const planLoadingEmojis = [
    "🥕",
    "🏋️",
    "⏲️",
    "💪",
    "🍲",
    "🤸",
    "🥦",
    "🏃",
    "🥘",
    "🧘",
    "🍲",
    "🚴",
    "🍽️",
    "🏆",
    "🌶️",
    "🥗",
];

const planLoadingPhrases = [
    "Chopping the carrots",
    "Racking the weights",
    "Preheating the oven",
    "Chalking the grips",
    "Simmering the sauce",
    "Setting up the squat rack",
    "Baking the broccoli",
    "Stretching the resistance bands",
    "Whisking the batter",
    "Tuning the cardio playlist",
    "Sautéing the veggies",
    "Warming up the kettlebells",
    "Plating the meal",
    "Dialing in your macros and reps",
    "Toasting the spices",
    "Mixing the dressing",
];

let planLoadingIntervalId = null;
let planLoadingStep = 0;
const PLAN_LOADING_CHANGE_MS = 4000;
const SERVICE_STATUS_POLL_EVENT = 'fitplan:service-status';

const createPlanControls = {
    button: null,
    checkbox: null,
    form: null,
};

function updatePlanLoadingOverlay() {
    const overlay = document.getElementById('loading-overlay');
    if (!overlay || overlay.hasAttribute('hidden')) {
        return;
    }

    const emojiEl = document.getElementById('loading-emoji');
    const textEl = document.getElementById('loading-text');

    const emoji = planLoadingEmojis[planLoadingStep % planLoadingEmojis.length];
    const phrase = planLoadingPhrases[planLoadingStep % planLoadingPhrases.length];

    if (emojiEl) {
        emojiEl.textContent = emoji;
    }

    if (textEl) {
        textEl.textContent = `${phrase}…`;
    }

    planLoadingStep += 1;
}

function showPlanLoadingOverlay() {
    const overlay = document.getElementById('loading-overlay');
    if (!overlay) return;

    const subtextEl = document.getElementById('loading-subtext');
    if (subtextEl) {
        subtextEl.textContent = 'Hang tight while we personalize your workouts and meals.';
    }

    planLoadingStep = Math.floor(Math.random() * planLoadingPhrases.length);
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    updatePlanLoadingOverlay();

    if (planLoadingIntervalId) {
        clearInterval(planLoadingIntervalId);
    }
    planLoadingIntervalId = window.setInterval(updatePlanLoadingOverlay, PLAN_LOADING_CHANGE_MS);
}

function hidePlanLoadingOverlay() {
    if (planLoadingIntervalId) {
        clearInterval(planLoadingIntervalId);
        planLoadingIntervalId = null;
    }

    const overlay = document.getElementById('loading-overlay');
    if (!overlay) return;

    overlay.hidden = true;
    overlay.setAttribute('aria-hidden', 'true');
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize form handlers
    initializeUnitSelectors();
    initializeGoalOptions();
    initializeMultiSelect();
    initializeFormValidation();
    initializeProgressSaving();
    initializeCreatePlanButton(); // ADD THIS LINE

    // Sync create plan button state with current service status
    const initialServiceDown = !!(window.FitPlanServiceStatus && window.FitPlanServiceStatus.down);
    updateCreatePlanAvailability(initialServiceDown, { force: true });

    window.addEventListener(SERVICE_STATUS_POLL_EVENT, (event) => {
        const isDown = !!(event.detail && event.detail.down);
        updateCreatePlanAvailability(isDown);
    });
});

// Validate height inputs
document.getElementById('basicInfoForm')?.addEventListener('submit', function(e) {
    const feet = parseInt(this.querySelector('input[name="height_feet"]').value);
    const inches = parseInt(this.querySelector('input[name="height_inches"]').value);
    
    if (feet < 3 || feet > 8) {
        e.preventDefault();
        alert('Please enter a valid height (3-8 feet)');
        return;
    }
    
    if (inches < 0 || inches > 11) {
        e.preventDefault();
        alert('Inches must be between 0 and 11');
        return;
    }
});

// Unit selector functionality (lbs/kg, ft/cm)
function initializeUnitSelectors() {
    const unitSelectors = document.querySelectorAll('.unit-selector');
    
    unitSelectors.forEach(selector => {
        const options = selector.querySelectorAll('.unit-option');
        
        options.forEach(option => {
            option.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Remove active class from siblings
                options.forEach(opt => opt.classList.remove('active'));
                
                // Add active class to clicked option
                this.classList.add('active');
                
                // Update placeholder or convert values if needed
                updateInputForUnit(this);
            });
        });
    });
}


function updateInputForUnit(unitOption) {
    const unit = unitOption.dataset.unit;
    const selector = unitOption.closest('.unit-selector');
    const input = selector.previousElementSibling;
    
    if (!input) return;
    
    // Update placeholder based on unit
    if (unit === 'kg' && input.name === 'weight') {
        input.placeholder = '68';
        input.step = '0.1';
    } else if (unit === 'lbs' && input.name === 'weight') {
        input.placeholder = '150';
        input.step = '1';
    } else if (unit === 'cm' && input.name === 'height') {
        input.placeholder = '173';
        input.pattern = '[0-9]+';
    } else if (unit === 'ft' && input.name === 'height') {
        input.placeholder = '5\'8"';
        input.pattern = '[0-9]+\'[0-9]+"';
    }
}

// Goal selection (radio buttons with custom styling)
function initializeGoalOptions() {
    const goalOptions = document.querySelectorAll('.goal-option');
    
    goalOptions.forEach(option => {
        const input = option.querySelector('input[type="radio"]');
        
        if (input) {
            // Set initial state
            if (input.checked) {
                option.classList.add('selected');
            }
            
            option.addEventListener('click', function() {
                // Remove selected class from all options in this group
                const groupName = input.name;
                const groupOptions = document.querySelectorAll(`input[name="${groupName}"]`);
                
                groupOptions.forEach(groupInput => {
                    const parentOption = groupInput.closest('.goal-option');
                    if (parentOption) {
                        parentOption.classList.remove('selected');
                    }
                });
                
                // Add selected class to clicked option
                this.classList.add('selected');
                input.checked = true;
                
                // Save progress
                saveCurrentStep();
            });
        }
    });
}

// Multi-select functionality (checkboxes)
function initializeMultiSelect() {
    const multiSelectOptions = document.querySelectorAll('.goal-option.multi-select');
    
    multiSelectOptions.forEach(option => {
        const input = option.querySelector('input[type="checkbox"]');
        
        if (input) {
            // Set initial state
            if (input.checked) {
                option.classList.add('selected');
            }
            
            option.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Handle "None" option - deselect others
                if (input.value === 'none') {
                    if (!input.checked) {
                        // Deselect all other options
                        const form = input.closest('form');
                        const otherInputs = form.querySelectorAll('input[type="checkbox"]:not([value="none"])');
                        otherInputs.forEach(otherInput => {
                            otherInput.checked = false;
                            const otherOption = otherInput.closest('.goal-option');
                            if (otherOption) {
                                otherOption.classList.remove('selected');
                            }
                        });
                    }
                } else {
                    // If selecting a specific option, deselect "None"
                    const form = input.closest('form');
                    const noneInput = form.querySelector('input[value="none"]');
                    if (noneInput && noneInput.checked) {
                        noneInput.checked = false;
                        const noneOption = noneInput.closest('.goal-option');
                        if (noneOption) {
                            noneOption.classList.remove('selected');
                        }
                    }
                }
                
                // Toggle current option
                input.checked = !input.checked;
                this.classList.toggle('selected', input.checked);
                
                // Save progress
                saveCurrentStep();
            });
        }
    });
}

// Form validation
function initializeFormValidation() {
    // Password confirmation validation
    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
        const passwordInput = signupForm.querySelector('input[name="password"]');
        const confirmInput = signupForm.querySelector('input[name="confirm_password"]');
        
        if (passwordInput && confirmInput) {
            function validatePasswords() {
                const errorMsg = confirmInput.nextElementSibling;
                
                if (passwordInput.value && confirmInput.value && 
                    passwordInput.value !== confirmInput.value) {
                    confirmInput.classList.add('error');
                    if (errorMsg && errorMsg.classList.contains('error-message')) {
                        errorMsg.style.display = 'block';
                    }
                    return false;
                } else {
                    confirmInput.classList.remove('error');
                    if (errorMsg && errorMsg.classList.contains('error-message')) {
                        errorMsg.style.display = 'none';
                    }
                    return true;
                }
            }
            
            confirmInput.addEventListener('input', validatePasswords);
            passwordInput.addEventListener('input', validatePasswords);
            
            signupForm.addEventListener('submit', function(e) {
                if (!validatePasswords()) {
                    e.preventDefault();
                }
            });
        }
    }
    
    // Age validation
    const ageInput = document.querySelector('input[name="age"]');
    if (ageInput) {
        ageInput.addEventListener('input', function() {
            const age = parseInt(this.value);
            if (age < 13 || age > 120) {
                this.classList.add('error');
            } else {
                this.classList.remove('error');
            }
        });
    }
    
    // Height format validation
    const heightInput = document.querySelector('input[name="height"]');
    if (heightInput) {
        heightInput.addEventListener('input', function() {
            const value = this.value;
            const activeUnit = document.querySelector('.unit-option.active[data-unit]');
            
            if (activeUnit) {
                const unit = activeUnit.dataset.unit;
                if (unit === 'ft' && value && !value.match(/^\d+'\d+"?$/)) {
                    this.classList.add('error');
                } else if (unit === 'cm' && value && !value.match(/^\d+$/)) {
                    this.classList.add('error');
                } else {
                    this.classList.remove('error');
                }
            }
        });
    }
}

// Progress saving
function initializeProgressSaving() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, select');
        
        inputs.forEach(input => {
            input.addEventListener('change', saveCurrentStep);
            if (input.type === 'text' || input.type === 'email' || input.type === 'number') {
                input.addEventListener('input', debounce(saveCurrentStep, 1000));
            }
        });
    });
    
    // Load saved progress on page load
    loadSavedProgress();
}

function saveCurrentStep() {
    const stepElement = document.querySelector('.step-indicator');
    if (!stepElement) return;
    
    const stepText = stepElement.textContent;
    const stepNumber = stepText.match(/Step (\d+)/);
    
    if (stepNumber) {
        const step = `step_${stepNumber[1]}`;
        const formData = {};
        
        // Collect all form data on the page
        const inputs = document.querySelectorAll('input, select');
        inputs.forEach(input => {
            if (input.name) {
                if (input.type === 'checkbox' || input.type === 'radio') {
                    if (input.checked) {
                        if (formData[input.name]) {
                            if (Array.isArray(formData[input.name])) {
                                formData[input.name].push(input.value);
                            } else {
                                formData[input.name] = [formData[input.name], input.value];
                            }
                        } else {
                            formData[input.name] = input.value;
                        }
                    }
                } else {
                    formData[input.name] = input.value;
                }
            }
        });
        
        if (window.FitPlan) {
            window.FitPlan.saveFormProgress(step, formData);
        }
    }
}

function loadSavedProgress() {
    if (!window.FitPlan) return;
    
    const stepElement = document.querySelector('.step-indicator');
    if (!stepElement) return;
    
    const stepText = stepElement.textContent;
    const stepNumber = stepText.match(/Step (\d+)/);
    
    if (stepNumber) {
        const step = `step_${stepNumber[1]}`;
        const savedData = window.FitPlan.getFormProgress(step);
        
        // Restore form values
        Object.keys(savedData).forEach(name => {
            const inputs = document.querySelectorAll(`[name="${name}"]`);
            
            inputs.forEach(input => {
                const value = savedData[name];
                
                if (input.type === 'checkbox' || input.type === 'radio') {
                    if (Array.isArray(value)) {
                        input.checked = value.includes(input.value);
                    } else {
                        input.checked = input.value === value;
                    }
                    
                    if (input.checked) {
                        const option = input.closest('.goal-option');
                        if (option) {
                            option.classList.add('selected');
                        }
                    }
                } else {
                    input.value = value || '';
                }
            });
        });
    }
}

// Utility function for debouncing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
// Create Plan Button Loading State
function initializeCreatePlanButton() {
    const createPlanForm = document.getElementById('createPlanForm');
    const createPlanButton = document.getElementById('createPlanBtn') || document.querySelector('.btn-create-plan');
    const privacyCheckbox = document.getElementById('privacyAccept');

    if (createPlanButton) {
        createPlanControls.button = createPlanButton;
        createPlanControls.checkbox = privacyCheckbox;
    }

    if (createPlanForm && createPlanButton) {
        createPlanControls.form = createPlanForm;

        createPlanForm.addEventListener('submit', function(e) {
            if (createPlanButton.dataset.serviceDown === 'true') {
                e.preventDefault();
                if (window.FitPlan && typeof window.FitPlan.showError === 'function') {
                    window.FitPlan.showError('Plan generation services are currently unavailable. Please try again later.');
                }
                return;
            }

            // Don't prevent default - let form submit; just add loading state
            setCreatePlanLoading(createPlanButton, true);
        });
    }

    if (createPlanButton && privacyCheckbox) {
        privacyCheckbox.addEventListener('change', function() {
            syncCreatePlanButtonState();
        });
    }

    syncCreatePlanButtonState();
}

function setCreatePlanLoading(button, isLoading) {
    if (!button || button.dataset.serviceDown === 'true') {
        return;
    }

    if (isLoading) {
        // Store original text
        button.dataset.originalText = button.textContent;
        
        // Add loading class
        button.classList.add('loading');
        button.disabled = true;
        
        // Change button content with spinner
        button.innerHTML = '<span class="btn-spinner"></span>Creating Plan...';
        // Prevent any future clicks or state changes
        button.style.pointerEvents = 'none';
        showPlanLoadingOverlay();

    } else {
        // Remove loading class
        button.classList.remove('loading');
        button.disabled = false;
        button.style.pointerEvents = '';
        // Restore original text
        button.textContent = button.dataset.originalText || 'Create My Plan';
        hidePlanLoadingOverlay();
    }
}

// Export for use in other contexts if needed
window.FitPlanButtons = window.FitPlanButtons || {};
window.FitPlanButtons.setCreatePlanLoading = setCreatePlanLoading;
window.FitPlanOverlay = {
    show: showPlanLoadingOverlay,
    hide: hidePlanLoadingOverlay
};
// Form submission with loading states
document.addEventListener('submit', function(e) {
    const submitBtn = e.target.querySelector('button[type="submit"], .btn-next');
    
    // Skip if this is the create plan button (it has its own handler)
    if (submitBtn && !submitBtn.classList.contains('btn-create-plan') && window.FitPlan) {
        window.FitPlan.setButtonLoading(submitBtn, true);
        
        // Reset loading state if form validation fails
        setTimeout(() => {
            if (e.defaultPrevented) {
                window.FitPlan.setButtonLoading(submitBtn, false);
            }
        }, 100);
    }
});

// Clear progress when completing onboarding
if (window.location.pathname.includes('dashboard')) {
    if (window.FitPlan) {
        window.FitPlan.clearFormProgress();
    }
}

function syncCreatePlanButtonState() {
    const { button, checkbox } = createPlanControls;
    if (!button) {
        return;
    }

    const serviceDown = button.dataset.serviceDown === 'true';

    if (serviceDown) {
        button.disabled = true;
        button.style.pointerEvents = 'none';
        if (checkbox) {
            checkbox.disabled = true;
        }
        hidePlanLoadingOverlay();
        return;
    }

    button.style.pointerEvents = '';
    if (checkbox) {
        checkbox.disabled = false;
        button.disabled = !checkbox.checked;
    } else {
        button.disabled = false;
    }
}

function updateCreatePlanAvailability(isDown, { force = false } = {}) {
    const { button } = createPlanControls;
    const note = document.getElementById('serviceUnavailableNote');

    if (note) {
        note.hidden = !isDown;
    }

    if (!button) {
        return;
    }

    const current = button.dataset.serviceDown === 'true';
    if (!force && current === isDown) {
        return;
    }

    button.dataset.serviceDown = isDown ? 'true' : 'false';
    syncCreatePlanButtonState();
}
