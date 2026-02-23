#
# Author: Javier Espigares Martin
#
# Secret Santa draw tool.
#
# Randomly assigns each participant one person to buy a gift for,
# honouring exclusion constraints (e.g. partners must not be paired).
#
# Participants are defined in a JSON file:
#   [{"name": "Alice", "not_allowed": ["Bob"], "email": "alice@example.com"}, ...]
#
# A message template (TXT or HTML) is sent/written for each participant.
# Use ^ as a placeholder for the giver's name and * for the receiver's name.
#
# Usage:
#   python secret_santa.py <list.json> <message.txt|.html> [-e] [-v]
#
import logging
import json
import os
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from random import choice


class SecretSanta:
    """
    Entry-point class for the Secret Santa draw.

    Parses command-line arguments, configures logging at three levels
    (console summary, console warnings, rotating file log), and hands off
    to :class:`Lottery` to run the full draw.

    Command-line interface::

        secret-santa <list> <message> [-e] [-v] [-vv]

    Arguments:
        list     Path to a JSON file listing all participants.
        message  Path to a TXT or HTML notification template.
        -e       Send email notifications to every participant via Gmail.
        -v       Verbose mode (INFO).  Use -vv for full debug output.

    The participants JSON file must follow this schema::

        [
          {"name": "Alice", "not_allowed": ["Bob"], "email": "alice@example.com"},
          ...
        ]

    In the message template:
        ``^`` is replaced with the giver's name.
        ``*`` is replaced with the receiver's name.
    """

    def __init__(self):
        self._args = None
        self._logger = logging.getLogger("SecretSanta")

        # Guard against duplicate handlers when the module is imported
        # multiple times (e.g. during testing).
        if not self._logger.handlers:
            # Plain one-line output for normal progress messages.
            normal_handler = logging.StreamHandler()
            normal_handler.setFormatter(logging.Formatter("%(message)s"))
            normal_handler.setLevel(logging.NOTSET)

            # Detailed format for warnings and errors on the console.
            debug_handler = logging.StreamHandler()
            debug_handler.setFormatter(logging.Formatter(
                "%(levelname)-8s [%(filename)s:%(lineno)d] %(funcName)s — %(message)s"
            ))
            debug_handler.setLevel(logging.WARNING)

            # File log captures everything regardless of verbosity flag.
            file_handler = logging.FileHandler("secret_santa.log")
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(filename)s:%(lineno)d] %(levelname)-8s %(message)s"
            ))
            file_handler.setLevel(logging.DEBUG)

            self._logger.addHandler(normal_handler)
            self._logger.addHandler(debug_handler)
            self._logger.addHandler(file_handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def main(self):
        """Parse arguments, configure verbosity, and run the lottery."""
        self._parse_args()

        level = logging.WARNING
        if self._args.verbosity >= 2:
            level = logging.DEBUG
        elif self._args.verbosity >= 1:
            level = logging.INFO

        self._logger.setLevel(level)
        self._logger.info("Starting Secret Santa draw")

        Lottery(
            self._args.list,
            self._args.message,
            send_email=self._args.email,
            logger=self._logger,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_args(self):
        """Build the argument parser, validate file paths, and store results."""
        parser = argparse.ArgumentParser(
            prog="secret-santa",
            description=(
                "Run a Secret Santa lottery that avoids pairing partners. "
                "Results are written to the 'out/' folder and optionally emailed."
            ),
        )
        parser.add_argument("list", help="Path to JSON file with participant list.")
        parser.add_argument("message", help="Path to TXT or HTML message template.")
        parser.add_argument(
            "-e", "--email",
            help="Send result emails to all participants via Gmail.",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "-v", "--verbosity",
            help="Increase verbosity (-v for INFO, -vv for DEBUG).",
            action="count",
            default=0,
        )

        args = parser.parse_args()

        if not os.path.isfile(args.list):
            self._logger.error("Participant file not found: %s", args.list)
            raise IOError("Participant file not found: {}".format(args.list))
        if not os.path.isfile(args.message):
            self._logger.error("Message template not found: %s", args.message)
            raise IOError("Message template not found: {}".format(args.message))

        self._args = args
        return args


class Person:
    """
    Represents a single Secret Santa participant.

    Attributes:
        name (str):        Display name used in output files and emails.
        email (str):       Email address for gift notifications.
        not_allowed (list[str]): Names this person must *not* be assigned to
                           gift — typically their partner or close family member.
        receiver (Person): The participant they will buy a gift for.
                           ``None`` until :meth:`assignReceiver` is called.
    """

    def __init__(self, name: str, not_allowed: list, email: str, logger):
        """
        Args:
            name:        Participant's display name.
            not_allowed: List of names excluded from being this person's receiver.
            email:       Participant's email address.
            logger:      Shared :class:`logging.Logger` instance.
        """
        self._logger = logger
        self._name = name
        self._not_allowed = not_allowed
        self._email = email
        self._receiver = None

        self._logger.debug("Created participant: %s (excluded: %s)", name, not_allowed)

    # ------------------------------------------------------------------
    # Special methods
    # ------------------------------------------------------------------

    def __str__(self):
        return self.message()

    def __repr__(self):
        return "Person({!r})".format(self._name)

    def __eq__(self, other):
        if not isinstance(other, Person):
            return NotImplemented
        return self._name == other._name

    def __hash__(self):
        return hash(self._name)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> str:
        return self._email

    @property
    def not_allowed(self) -> list:
        return self._not_allowed

    @property
    def receiver(self):
        return self._receiver

    @receiver.setter
    def receiver(self, value):
        self._receiver = value

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def message(self) -> str:
        """Return a human-readable summary of this participant's assignment."""
        if self._receiver is None:
            return "Name: {}\nReceiver: (not yet assigned)\nEmail: {}".format(
                self._name, self._email
            )
        return "Name: {}\nReceiver: {}\nEmail: {}".format(
            self._name, self._receiver.name, self._email
        )

    def is_receiver_ok(self, receiver) -> bool:
        """
        Check whether *receiver* is a valid gift target for this person.

        A receiver is invalid when:
        - they are the same person (self-gifting), or
        - their name appears in this person's ``not_allowed`` list.

        Args:
            receiver (Person): Candidate receiver.

        Returns:
            ``True`` if the pairing is allowed, ``False`` otherwise.
        """
        if receiver == self:
            self._logger.debug("%s cannot buy for themselves", self._name)
            return False
        if receiver.name in self._not_allowed:
            self._logger.debug(
                "%s cannot buy for %s (excluded)", self._name, receiver.name
            )
            return False
        self._logger.debug("%s can buy for %s", self._name, receiver.name)
        return True

    def assign_receiver(self, receiver):
        """
        Assign *receiver* as the person this participant will buy a gift for.

        Args:
            receiver (Person): The chosen recipient.
        """
        self._receiver = receiver
        self._logger.debug("%s → %s", self._name, receiver.name)

    def write_file(self, directory: str):
        """
        Write a ``<name>.txt`` file containing the assignment to *directory*.

        The directory is created automatically if it does not already exist.

        Args:
            directory: Path to the output directory (e.g. ``"out"``).
        """
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, self._name + ".txt")
        with open(path, "w") as fh:
            self._logger.info("Writing result file: %s", path)
            fh.write(self.message())

    def send_email(self, template: str):
        """
        Send the gift-assignment notification to this participant via Gmail SMTP.

        **Credentials** are read from environment variables — never hard-code
        passwords in source code:

        ``SANTA_EMAIL_ADDRESS``
            The Gmail address used to send emails.
        ``SANTA_EMAIL_PASSWORD``
            A Gmail *App Password* (16-character code, **not** your regular
            account password).  See
            https://support.google.com/accounts/answer/185833 for setup
            instructions.

        **Placeholder substitution** in the template:

        ``^``
            Replaced with this person's name (the giver).
        ``*``
            Replaced with the receiver's name.

        The template may be plain text or HTML — it is always sent as
        ``text/html`` so that HTML formatting renders correctly.

        Args:
            template: Raw message template with ``^`` and ``*`` placeholders.

        Raises:
            EnvironmentError: If the required environment variables are not set.
            smtplib.SMTPException: If the email cannot be delivered.
        """
        sender = os.environ.get("SANTA_EMAIL_ADDRESS")
        password = os.environ.get("SANTA_EMAIL_PASSWORD")

        if not sender or not password:
            raise EnvironmentError(
                "Set the SANTA_EMAIL_ADDRESS and SANTA_EMAIL_PASSWORD "
                "environment variables before using the -e flag.\n"
                "Gmail requires an App Password — see "
                "https://support.google.com/accounts/answer/185833"
            )

        self._logger.info("Sending email to %s <%s>", self._name, self._email)

        body = template.replace("^", self._name).replace("*", self._receiver.name)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Secret Santa assignment"
        msg["From"] = sender
        msg["To"] = self._email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, self._email, msg.as_string())

        self._logger.info("Email sent to %s", self._email)


class Bucket:
    """
    Manages the pool of available recipients and runs the draw algorithm.

    The algorithm uses **randomised backtracking**:

    1. All participants are placed in a candidate pool.
    2. For each giver (in original order), a random candidate is drawn.
    3. The candidate is validated against the giver's ``not_allowed`` list
       and the self-gifting rule.
    4. If valid, the candidate is removed from the pool and assigned.
    5. If a single giver exhausts too many attempts (**deadlock**), the
       entire draw is discarded — all receiver assignments are reset — and
       the process restarts from step 1.
    6. The loop continues until every participant has a valid assignment.

    This guarantees a uniformly random result that satisfies all constraints.
    """

    def __init__(self, people: list, logger):
        """
        Run the draw, retrying until a valid full assignment is found.

        Args:
            people: List of :class:`Person` objects to assign.
            logger: Shared :class:`logging.Logger` instance.
        """
        self._logger = logger
        self._people = people
        self._len = len(people)

        attempts = 0
        while not self._draw():
            attempts += 1
            self._logger.debug("Restarting draw (attempt %d)", attempts)

        self._logger.info("Draw completed after %d restart(s)", attempts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _draw(self) -> bool:
        """
        Attempt one complete draw over all participants.

        Returns:
            ``True`` if every participant was successfully assigned,
            ``False`` if a deadlock was detected and the draw must be retried.
        """
        # Fresh copy of the candidate pool for this attempt.
        candidates = list(self._people)

        for giver in self._people:
            result = self._pick(giver, candidates)
            if result is None:
                # Deadlock — reset all partial assignments before retrying.
                for person in self._people:
                    person.receiver = None
                return False
            candidates = result

        success = len(candidates) == 0
        self._logger.debug("Draw result: success=%s", success)
        return success

    def _pick(self, giver, candidates: list):
        """
        Randomly select and assign a valid receiver for *giver*.

        Args:
            giver:      The :class:`Person` who will be buying a gift.
            candidates: Remaining pool of unassigned recipients.

        Returns:
            The updated *candidates* list with the assigned receiver removed,
            or ``None`` if a deadlock was detected (too many failed attempts).
        """
        self._logger.debug("Finding receiver for %s", giver.name)

        # Allow slightly more attempts than there are candidates to account
        # for unlucky random sequences before declaring a deadlock.
        max_attempts = self._len + 1

        for attempt in range(max_attempts):
            candidate = choice(candidates)
            if giver.is_receiver_ok(candidate):
                giver.assign_receiver(candidate)
                candidates.remove(candidate)
                self._logger.debug("Remaining pool: %s", candidates)
                return candidates

        # Could not find a valid receiver within the attempt budget.
        self._logger.debug(
            "Deadlock: no valid receiver found for %s after %d attempts",
            giver.name, max_attempts,
        )
        return None


class Lottery:
    """
    Orchestrates the complete Secret Santa draw.

    Loads participants from a JSON file, triggers the draw via :class:`Bucket`,
    then writes per-person result files and (optionally) sends email
    notifications to every participant.

    JSON file format::

        [
          {
            "name":        "Alice",
            "not_allowed": ["Bob"],
            "email":       "alice@example.com"
          },
          ...
        ]
    """

    def __init__(
        self,
        people_file: str,
        template_file: str,
        send_email: bool,
        logger,
        output_dir: str = "out",
    ):
        """
        Load data, run the draw, and deliver results.

        Args:
            people_file:   Path to the participants JSON file.
            template_file: Path to the TXT or HTML message template.
            send_email:    When ``True``, send email notifications to every
                           participant after the draw.
            logger:        Shared :class:`logging.Logger` instance.
            output_dir:    Directory where per-person ``.txt`` files are written.
                           Created automatically if absent.  Defaults to ``"out"``.
        """
        self._logger = logger

        # Load the message template.
        with open(template_file, "r") as fh:
            self._template = fh.read()
        self._logger.debug("Loaded message template from: %s", template_file)

        # Load and parse the participants list.
        with open(people_file, "r") as fh:
            raw = json.load(fh)

        self._people = [
            Person(
                entry["name"],
                entry.get("not_allowed", []),
                entry["email"],
                self._logger,
            )
            for entry in raw
        ]
        self._logger.info("Loaded %d participants", len(self._people))

        # Run the draw — Bucket assigns receivers to every Person in place.
        Bucket(self._people, logger)

        # Report and deliver results.
        self._logger.info("Draw results:")
        for person in self._people:
            self._logger.info("  %s → %s", person.name, person.receiver.name)
            person.write_file(output_dir)
            if send_email:
                person.send_email(self._template)

        self._logger.info(
            "Done. Result files written to '%s/'.", output_dir
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Console-script entry point (registered by pip as ``secret-santa``)."""
    SecretSanta().main()


if __name__ == "__main__":
    main()
