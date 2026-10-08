"""Windows HTTP(S) opening without a command shell or legacy tool imports."""

import asyncio
import os
import sys

from pydantic import BaseModel

from ...domain.action import CapabilityName
from ...domain.tool_inputs import UrlOpenInput
from ...domain.tool_outputs import NoDataOutput


class WindowsUrlOpenProvider:
    """An explicitly injected ToolProvider for url.open only."""

    async def execute(self, capability: CapabilityName, input_data: BaseModel) -> NoDataOutput:
        if capability != "url.open":
            raise KeyError(capability)
        if sys.platform != "win32":
            raise OSError("Windows URL opening requires a Windows host")
        # Reuse the Domain contract, including revalidation of unvalidated model
        # construction/copies; never implement separate URL rules at this boundary.
        payload = UrlOpenInput.model_validate(input_data)
        await asyncio.to_thread(os.startfile, str(payload.url), "open")
        # Native launch returning is not evidence that the browser loaded the page.
        return NoDataOutput()
