# SPDX-License-Identifier: MIT
"""Interface modules aggregating protocols for pyqa subsystems.

This package intentionally avoids importing concrete implementations to
preserve strict dependency inversion; import the specific interface modules
(e.g. ``pyqa.interfaces.analysis``) directly instead of relying on re-exports.
"""

__all__: tuple[str, ...] = ()
