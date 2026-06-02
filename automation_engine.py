import logging
import time
import secrets
import string
from playwright.sync_api import Page, Locator
import storage_manager
import config

logger = logging.getLogger(__name__)

# Semantic mapping of profile keys to possible label/placeholder texts
SEMANTIC_MAP = {
    "first_name": ["First Name", "Given Name", "first name", "given name", "first_name", "fname"],
    "last_name": ["Last Name", "Family Name", "Surname", "last name", "family name", "last_name", "lname"],
    "email": ["Email", "Email Address", "email", "email_address", "email address"],
    "phone": ["Phone", "Phone Number", "Mobile", "Mobile Phone", "phone", "phone_number", "telephone"],
    "current_city": ["City", "Current City", "Town", "city", "current_city"],
    "current_state": ["State", "Province", "Region", "State/Province", "state", "state_province"],
    "linkedin": ["LinkedIn", "LinkedIn Profile", "LinkedIn URL", "linkedin", "linkedin_profile"],
    "github": ["GitHub", "GitHub Profile", "GitHub URL", "github", "github_profile"],
    "portfolio": ["Portfolio", "Website", "Personal Website", "portfolio", "website", "portfolio_url"],
    "experience_years": ["Experience", "Years of Experience", "How many years", "experience_years"],
    "highest_degree": ["Highest Degree", "Degree", "Education", "highest_degree", "degree"],
    "notice_period": ["Notice Period", "Availability", "notice_period", "availability"]
}

def generate_secure_password() -> str:
    """Generates a password that complies with Workday's complexity rules (capital, lowercase, number, special)."""
    alphabet = string.ascii_letters + string.digits
    special = "!@#$%^&*"
    # Ensure at least one of each class
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(special)
    ]
    # Add random characters for the rest
    pwd += [secrets.choice(alphabet + special) for _ in range(10)]
    secrets.SystemRandom().shuffle(pwd)
    return "AppPwd_" + "".join(pwd) + "9!"

def label_to_key(label: str) -> str:
    """Converts a form field label to a snake_case key for profile.json."""
    clean = "".join(c for c in label if c.isalnum() or c.isspace()).strip().lower()
    return "_".join(clean.split())

def find_form_field(page: Page, profile_key: str) -> Locator:
    """
    Attempts to locate a visible input, select, or textarea using Playwright's 
    semantic locators based on the lists of labels associated with the profile_key.
    """
    labels = SEMANTIC_MAP.get(profile_key, [])
    
    # Try locating by label
    for label in labels:
        locator = page.get_by_label(label, exact=False)
        try:
            if locator.first.is_visible(timeout=300):
                return locator.first
        except Exception:
            pass
            
    # Try locating by placeholder
    for label in labels:
        locator = page.get_by_placeholder(label, exact=False)
        try:
            if locator.first.is_visible(timeout=300):
                return locator.first
        except Exception:
            pass

    # Try locating by aria-label attribute matching
    for label in labels:
        # Build locator matching aria-label
        locator = page.locator(f"[aria-label*='{label}' i]")
        try:
            if locator.first.is_visible(timeout=300):
                return locator.first
        except Exception:
            pass

    return None

def fill_field(locator: Locator, value: str):
    """Fills a field depending on its element tag type."""
    tag_name = locator.evaluate("element => element.tagName.toLowerCase()")
    type_attr = locator.get_attribute("type") or ""
    type_attr = type_attr.lower()
    
    if tag_name == "input" and type_attr == "file":
        locator.set_input_files(value)
    elif tag_name == "input" and type_attr in ("checkbox", "radio"):
        if value and str(value).lower() not in ("false", "no", "0"):
            locator.check()
    elif tag_name == "select":
        try:
            locator.select_option(label=str(value))
        except Exception:
            try:
                locator.select_option(value=str(value))
            except Exception:
                # Custom selection click handler could go here if select options are hidden/custom
                pass
    else:
        # Standard text input or textarea
        locator.fill(str(value))

def upload_resume(page: Page) -> bool:
    """Attempts to find file upload inputs for the resume and uploads config.RESUME_PATH."""
    if not config.RESUME_PATH.exists():
        logger.warning("Resume file does not exist, skipping upload.")
        return False
        
    try:
        # Find all file input elements
        file_inputs = page.locator("input[type='file']").all()
        for file_input in file_inputs:
            name = (file_input.get_attribute("name") or "").lower()
            id_attr = (file_input.get_attribute("id") or "").lower()
            
            # Identify if it is a resume upload
            is_resume = "resume" in name or "cv" in name or "resume" in id_attr or "cv" in id_attr or len(file_inputs) == 1
            if is_resume:
                file_input.set_input_files(str(config.RESUME_PATH))
                logger.info("Successfully uploaded resume to file input.")
                return True
                
        # If no native input worked, check for click-based triggers that open file chooser
        upload_triggers = ["upload resume", "upload cv", "attach resume", "select file", "upload document"]
        for trigger in upload_triggers:
            locator = page.get_by_text(trigger, exact=False)
            try:
                if locator.first.is_visible(timeout=500):
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        locator.first.click()
                    file_chooser = fc_info.value
                    file_chooser.set_files(str(config.RESUME_PATH))
                    logger.info(f"Uploaded resume via file chooser: '{trigger}'")
                    return True
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed resume uploading attempt: {e}")
        
    return False

def get_visible_required_fields(page: Page) -> list[dict]:
    """Scans the page for visible input fields that are marked required or have required labels."""
    required_elements = []
    
    # Target standard input, select, and textarea fields
    elements = page.locator("input, select, textarea").all()
    for el in elements:
        try:
            if not el.is_visible(timeout=200):
                continue
                
            is_req = el.evaluate("""element => {
                if (element.hasAttribute('required') || element.getAttribute('aria-required') === 'true') {
                    return true;
                }
                // Check surrounding labels
                const id = element.id;
                let label = null;
                if (id) {
                    label = document.querySelector(`label[for="${id}"]`);
                }
                if (!label) {
                    label = element.closest('label') || element.previousElementSibling;
                }
                if (label && (label.innerText.includes('*') || label.innerText.toLowerCase().includes('required'))) {
                    return true;
                }
                return false;
            }""")
            
            if is_req:
                # Capture metadata context for prompting the user
                label_text = el.evaluate("""element => {
                    const id = element.id;
                    let label = null;
                    if (id) {
                        label = document.querySelector(`label[for="${id}"]`);
                    }
                    if (!label) {
                        label = element.closest('label') || element.previousElementSibling;
                    }
                    return label ? label.innerText.trim() : '';
                }""")
                placeholder = el.get_attribute("placeholder") or ""
                name_attr = el.get_attribute("name") or ""
                
                required_elements.append({
                    "locator": el,
                    "label": label_text,
                    "placeholder": placeholder,
                    "name": name_attr
                })
        except Exception:
            pass
            
    return required_elements

def fill_form_with_learning_loop(page: Page):
    """
    Main loop for filling out a form page. It fills fields found in profile.json,
    scans for unmapped required fields, and queries the user via CLI to learn missing details.
    """
    profile = storage_manager.load_profile()
    
    # 1. Fill fields using known semantic matches
    for key, value in profile.items():
        if isinstance(value, list):
            value_str = ", ".join(value)
        else:
            value_str = str(value)
            
        locator = find_form_field(page, key)
        if locator:
            try:
                # Check if it has a value already
                current_val = locator.evaluate("element => element.value")
                if not current_val:
                    fill_field(locator, value_str)
                    page.wait_for_timeout(100)
            except Exception:
                pass
                
    # 2. Upload resume if file inputs exist
    upload_resume(page)
    
    # 3. Detect unmapped required fields and trigger Learning Loop
    required_fields = get_visible_required_fields(page)
    for field in required_fields:
        locator = field["locator"]
        try:
            # Check if it's currently empty
            tag_name = locator.evaluate("element => element.tagName.toLowerCase()")
            type_attr = locator.get_attribute("type") or ""
            type_attr = type_attr.lower()
            
            if tag_name == "input" and type_attr in ("checkbox", "radio"):
                if locator.is_checked():
                    continue
            else:
                val = locator.evaluate("element => element.value")
                if val and val.strip():
                    continue
            
            # Required and currently empty. Prompt user!
            label = field["label"] or field["placeholder"] or field["name"] or "unlabeled_field"
            key = label_to_key(label)
            
            # Check if this new key was already saved in this session's profile
            updated_profile = storage_manager.load_profile()
            if key in updated_profile:
                fill_field(locator, updated_profile[key])
                continue
                
            print(f"\n[Learning Loop Required] Missing information for form submission.")
            print(f"URL: {page.url}")
            print(f"Context Label: '{label}'")
            print(f"Placeholder: '{field['placeholder']}'")
            print(f"Name Attribute: '{field['name']}'")
            
            user_input = input(f"Enter the value for '{label}' (to save in profile.json under '{key}'): ").strip()
            if user_input:
                storage_manager.update_profile_field(key, user_input)
                fill_field(locator, user_input)
                page.wait_for_timeout(200)
            else:
                print("Skipped field input.")
        except Exception as e:
            logger.error(f"Error executing learning loop on field: {e}")

class ATSAutomationEngine:
    def __init__(self, page: Page):
        self.page = page



    def identify_ats(self, url: str) -> str:
        """
        Determines the ATS system based on the URL hostname only.

        IMPORTANT: We intentionally do NOT search the full page body/content for
        ATS keywords.  Full-page content scanning causes catastrophic false positives
        because social-media pages, classified sites, and ad-supported pages routinely
        embed Workday/Lever/Greenhouse script tags or tracking pixels even when the
        page itself is not an ATS form at all (the Facebook/Eduport failure was caused
        exactly by this).

        Identification order:
          1. Known unsupported domains → 'unsupported'
          2. Exact ATS subdomain patterns in the URL → specific ATS name
          3. Everything else → 'generic'
        """
        try:
            from urllib.parse import urlparse
            hostname = urlparse(url).hostname or ""
        except Exception:
            hostname = ""
        hostname_lower = hostname.lower()
        url_lower = url.lower()

        # --- Step 1: Unsupported domain blocklist (sourced from config.py) ---
        for domain in config.UNSUPPORTED_DOMAINS:
            if hostname_lower == domain or hostname_lower.endswith("." + domain):
                logger.info(f"Domain '{hostname}' is on the unsupported blocklist. Skipping.")
                return "unsupported"

        # --- Step 2: Known ATS platforms (URL-hostname checks only) ---
        # Workday: subdomains of myworkdayjobs.com (e.g. company.myworkdayjobs.com)
        if "myworkdayjobs.com" in hostname_lower:
            return "workday"
        # Lever: jobs.lever.co
        if hostname_lower == "jobs.lever.co" or hostname_lower.endswith(".lever.co"):
            return "lever"
        # Greenhouse: boards.greenhouse.io or job-boards.greenhouse.io
        if "greenhouse.io" in hostname_lower:
            return "greenhouse"
        # iCIMS
        if "icims.com" in hostname_lower:
            return "generic"  # Handled by generic fallback for now
        # SmartRecruiters
        if "smartrecruiters.com" in hostname_lower:
            return "generic"

        # --- Step 3: Default to generic ---
        return "generic"

    def apply(self, url: str):
        """Orchestrates the entire application flow for a single URL."""
        # Identify ATS *before* navigating so unsupported sites are skipped cheaply.
        ats = self.identify_ats(url)
        logger.info(f"Identified ATS portal as: '{ats.upper()}' for URL: {url}")

        if ats == "unsupported":
            raise Exception(
                f"URL belongs to an unsupported / non-ATS domain and was skipped. "
                f"Site: {url}"
            )

        logger.info(f"Navigating to job application page: {url}")
        self.page.goto(url)
        self.page.wait_for_load_state("load")

        if ats == "workday":
            self.handle_workday(url)
        elif ats == "lever":
            self.handle_lever()
        elif ats == "greenhouse":
            self.handle_greenhouse()
        else:
            self.handle_generic()

    def handle_workday(self, url: str):
        """Automates account registration, OTP handling, and form stages of Workday."""
        # Step 1: Handle initial Apply click
        logger.info("Looking for Apply button...")
        apply_btn = self.page.get_by_role("button", name="Apply", exact=False)
        if not apply_btn.first.is_visible(timeout=5000):
            # Check for generic apply link or button
            apply_btn = self.page.locator("a:has-text('Apply')").first
            
        if apply_btn.is_visible(timeout=5000):
            apply_btn.click()
            self.page.wait_for_load_state("load")
            
        # Workday usually prompts: "Apply Manually", "Autofill with Resume"
        manual_btn = self.page.get_by_role("button", name="Apply Manually", exact=False)
        if manual_btn.first.is_visible(timeout=3000):
            manual_btn.first.click()
            self.page.wait_for_load_state("load")
            
        # Step 2: Sign In / Create Account Page
        create_acc_btn = self.page.get_by_role("button", name="Create Account", exact=False)
        if not create_acc_btn.first.is_visible(timeout=3000):
            create_acc_btn = self.page.get_by_text("Create Account", exact=False).first
            
        if create_acc_btn.is_visible(timeout=3000):
            logger.info("Registering a new account...")
            create_acc_btn.click()
            self.page.wait_for_load_state("load")
            
            # Fill Registration Details
            profile = storage_manager.load_profile()
            email = profile["email"]
            password = generate_secure_password()
            
            # Locate fields semantically
            email_field = self.page.get_by_label("Email Address", exact=False).first
            pwd_field = self.page.get_by_label("Password", exact=False).first
            confirm_pwd_field = self.page.get_by_label("Confirm Password", exact=False).first
            
            if email_field.is_visible(timeout=3000):
                email_field.fill(email)
            if pwd_field.is_visible(timeout=3000):
                pwd_field.fill(password)
            if confirm_pwd_field.is_visible(timeout=3000):
                confirm_pwd_field.fill(password)
                
            # Accept Terms Checkbox
            terms_chk = self.page.get_by_label("I agree", exact=False).first
            if not terms_chk.is_visible(timeout=1000):
                # Search for input checkbox
                terms_chk = self.page.locator("input[type='checkbox']").first
                
            if terms_chk.is_visible(timeout=2000):
                terms_chk.check()
                
            # Submit Registration
            register_submit = self.page.get_by_role("button", name="Create Account", exact=True)
            if not register_submit.first.is_visible(timeout=1000):
                register_submit = self.page.locator("button:has-text('Create Account')").first
                
            register_submit.click()
            self.page.wait_for_load_state("load")
            
            # Log Credentials locally
            storage_manager.log_credentials(url, email, password)
            
            # OTP / Identity Verification Check
            self.page.wait_for_timeout(2000)
            content_lower = self.page.content().lower()
            if "verify" in content_lower or "one-time passcode" in content_lower or "otp" in content_lower or "verification code" in content_lower:
                print("\n[OTP/Verification Required] Workday has prompted for an identity verification code.")
                otp = input("Please check your email and enter the OTP/Verification Code: ").strip()
                
                # Locate OTP field semantically
                otp_field = self.page.get_by_label("code", exact=False).first
                if not otp_field.is_visible(timeout=2000):
                    otp_field = self.page.get_by_placeholder("code", exact=False).first
                if not otp_field.is_visible(timeout=1000):
                    otp_field = self.page.locator("input[type='text']").first
                    
                otp_field.fill(otp)
                
                # Submit OTP
                otp_submit = self.page.get_by_role("button", name="Submit", exact=False).first
                if not otp_submit.is_visible(timeout=1000):
                    otp_submit = self.page.locator("button:has-text('Submit')").first
                otp_submit.click()
                self.page.wait_for_load_state("load")

        # Step 3: Loop through multi-page application form steps
        logger.info("Starting form stages...")
        steps_limit = 12
        for step in range(steps_limit):
            self.page.wait_for_timeout(2000)
            
            # Fill out the fields visible on this page (and trigger learning loop for required fields)
            fill_form_with_learning_loop(self.page)
            
            # Check if this is the final Review step
            # Typically, Workday final steps display 'Submit' button
            submit_btn = self.page.get_by_role("button", name="Submit", exact=True).first
            if not submit_btn.is_visible(timeout=1000):
                submit_btn = self.page.locator("button:has-text('Submit Application')").first
                
            # If the submit button is present and we don't see any "Save and Continue" buttons, we are on the review page
            next_btn = self.page.get_by_role("button", name="Save and Continue", exact=False).first
            if not next_btn.is_visible(timeout=1000):
                next_btn = self.page.get_by_role("button", name="Next", exact=True).first
            if not next_btn.is_visible(timeout=1000):
                next_btn = self.page.get_by_role("button", name="Continue", exact=True).first

            if submit_btn.is_visible(timeout=1000) and not next_btn.is_visible(timeout=1000):
                # We have reached the final submit page!
                self.safe_submit(submit_btn)
                return
                
            if next_btn.is_visible(timeout=1000):
                logger.info(f"Moving to next page (Step {step + 1})...")
                next_btn.click()
                self.page.wait_for_load_state("load")
            else:
                # If there is neither a next button nor a submit button visible, we might be stuck or done.
                # Let's see if we see "Submit" button anyway and click it if visible
                if submit_btn.is_visible(timeout=1000):
                    self.safe_submit(submit_btn)
                    return
                else:
                    logger.warning("Neither Next nor Submit button found. Form filling might have hit an unexpected layout.")
                    break
        
        raise Exception("Failed to reach final submit page within step limit.")

    def handle_lever(self):
        """Automates application on Lever single-page forms."""
        # Wait for form to load
        self.page.wait_for_selector("form", timeout=10000)
        
        # Fill form
        fill_form_with_learning_loop(self.page)
        
        # Identify submit button
        submit_btn = self.page.get_by_role("button", name="Submit Application", exact=False).first
        if not submit_btn.is_visible(timeout=1000):
            submit_btn = self.page.locator("button[type='submit']").first
            
        if submit_btn.is_visible(timeout=2000):
            self.safe_submit(submit_btn)
        else:
            raise Exception("Submit button not found on Lever form.")

    def handle_greenhouse(self):
        """Automates application on Greenhouse single-page forms."""
        # Wait for form
        self.page.wait_for_selector("form#application_form, form", timeout=10000)
        
        # Fill form
        fill_form_with_learning_loop(self.page)
        
        # Identify submit button
        submit_btn = self.page.get_by_role("button", name="Submit Application", exact=True).first
        if not submit_btn.is_visible(timeout=1000):
            submit_btn = self.page.locator("#submit_app, button[type='submit']").first
            
        if submit_btn.is_visible(timeout=2000):
            self.safe_submit(submit_btn)
        else:
            raise Exception("Submit button not found on Greenhouse form.")

    def handle_generic(self):
        """
        Attempt generic form filling and submission.

        Submit-button detection uses a broad, prioritised list of selectors so that
        portals with non-standard markup (JobResultHub, custom career pages, etc.)
        are still handled correctly.
        """
        logger.info("Attempting generic form filling...")
        self.page.wait_for_timeout(3000)

        fill_form_with_learning_loop(self.page)

        # -----------------------------------------------------------------------
        # Ordered list of submit-button selectors, from most-specific to broadest.
        # Each entry is either a CSS selector string or a tuple (strategy, value)
        # where strategy is 'role' (uses get_by_role) or 'text' (uses get_by_text).
        # -----------------------------------------------------------------------
        SUBMIT_SELECTORS = [
            # --- Native HTML submit controls (highest confidence) ---
            "button[type='submit']",
            "input[type='submit']",

            # --- Semantic role + common submit labels ---
            ("role", "Submit"),
            ("role", "Submit Application"),
            ("role", "Apply Now"),
            ("role", "Apply"),
            ("role", "Send Application"),
            ("role", "Post Application"),
            ("role", "Complete Application"),
            ("role", "Finish Application"),

            # --- CSS :has-text matchers for <button> ---
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
            "button:has-text('Send Application')",
            "button:has-text('Post Application')",
            "button:has-text('Complete Application')",
            "button:has-text('Finish')",
            "button:has-text('Send')",

            # --- <input type='button'> variants ---
            "input[type='button'][value*='Submit' i]",
            "input[type='button'][value*='Apply' i]",

            # --- <a> tag submit-like links ---
            "a:has-text('Submit Application')",
            "a:has-text('Apply Now')",
            "a:has-text('Submit')",
            "a[role='button']:has-text('Apply')",

            # --- aria-label fallback ---
            "[aria-label*='submit' i]",
            "[aria-label*='apply' i]",
        ]

        for selector in SUBMIT_SELECTORS:
            try:
                if isinstance(selector, tuple):
                    # Use get_by_role for semantic role-based lookups
                    _, label = selector
                    submit_btn = self.page.get_by_role("button", name=label, exact=False).first
                else:
                    submit_btn = self.page.locator(selector).first

                if submit_btn.is_visible(timeout=600):
                    logger.info(f"Generic submit button found via selector: {selector!r}")
                    self.safe_submit(submit_btn)
                    return
            except Exception:
                pass

        raise Exception("Submit button could not be identified on generic portal.")

    def safe_submit(self, submit_button: Locator):
        """Pauses for 3 seconds to allow user inspection/override, then clicks submit."""
        logger.info("Safe Submission Phase: Pausing for 3 seconds...")
        print("\n--- SAFE SUBMISSION PAUSE ---")
        print("Application is complete! Pausing for 3 seconds before submitting.")
        print("You can manually inspect the page or intervene now if needed.")
        print("-----------------------------")
        
        time.sleep(3)
        
        logger.info("Clicking final submit button...")
        submit_button.click()
        self.page.wait_for_load_state("load")
        self.page.wait_for_timeout(3000)
        
        # Final success logging will be handled in the main orchestrator loop
        logger.info("Form submission clicked successfully.")
