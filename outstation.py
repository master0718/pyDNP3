import pydnp3
from pydnp3 import opendnp3, openpal, asiodnp3, asiopal

# Initialize the DNP3 manager
manager = asiodnp3.DNP3Manager(1)

# Callback for receiving log messages
class LogHandler(openpal.ILogHandler):
    def OnMessage(self, log_entry):
        print(log_entry.message)

log_handler = LogHandler()

# Callback for channel state changes
class ChannelListener(asiodnp3.IChannelListener):
    def OnStateChange(self, state):
        print(f"Channel state changed: {state}")

    def OnOpen(self):
        print("Channel opened")

    def OnClose(self):
        print("Channel closed")

    def OnSendResult(self, num_bytes):
        print(f"Sent {num_bytes} bytes")

    def OnReceive(self, header, body):
        if isinstance(header, opendnp3.LPDU) and header.control.FUNC_CODE == opendnp3.FunctionCode.RESET_LINK_STATES:
            print("RESET_LINK_STATES command received")
        print(f"Received: {header}, {body}")

channel_listener = ChannelListener()

# Create a channel and bind to a specific IP address
print("Creating TCP server channel")
channel = manager.AddTCPServer(
    "tcpserver",
    opendnp3.levels.ALL_COMMS,
    asiopal.ChannelRetry.Default(),
    "10.255.254.6",
    20000,
    channel_listener
)
print("TCP server channel created")

# Callback for handling command requests
class CommandHandler(opendnp3.ICommandHandler):
    def __init__(self):
        super().__init__()
        self.selected_index = None
        print("CommandHandler initialized")

    def Start(self):
        print("CommandHandler Start")

    def End(self):
        print("CommandHandler End")

    def Select(self, command, index, op_type):
        print(f"Select command: {command}, index: {index}, type: {op_type}")
        if isinstance(command, opendnp3.AnalogOutputInt16) and (index == 0 or index == 1):
            self.selected_index = index
            print(f"Selected index: {self.selected_index}")
            return opendnp3.CommandStatus.SUCCESS
        return opendnp3.CommandStatus.NOT_SUPPORTED

    def Operate(self, command, index, op_type):
        print(f"Operate command: {command}, index: {index}, type: {op_type}")
        if isinstance(command, opendnp3.AnalogOutputInt16) and self.selected_index == index:
            value = command.value
            builder = asiodnp3.UpdateBuilder()
            analog = opendnp3.Analog(value, opendnp3.Flags(opendnp3.AnalogQuality.ONLINE), opendnp3.DNPTime(0))
            print(f"Analog value: {value}")
            if index == 0:  # ATLAS_SETPOINT_INSTRUCTION
                builder.Update(analog, 4)  # Update ATLAS_SETPOINT_INSTRUCTION
                outstation.Apply(builder.Build())
                builder.Update(analog, 6)  # Echo the value to ATLAS_SETPOINT_INSTRUCTION.oper
                outstation.Apply(builder.Build())
            elif index == 1:  # ATLAS_SETPOINT_INSTRUCTION.status
                builder.Update(analog, 1)  # Update ATLAS_SETPOINT_ECHO
                outstation.Apply(builder.Build())
                builder.Update(analog, 5)  # Update ATLAS_SETPOINT_INSTRUCTION.status
                outstation.Apply(builder.Build())
            self.selected_index = None
            return opendnp3.CommandStatus.SUCCESS
        return opendnp3.CommandStatus.NO_SELECT

    def DirectOperate(self, command, index, op_type):
        print(f"DirectOperate command: {command}, index: {index}, type: {op_type}")
        return self.Operate(command, index, op_type)

    def Perform(self, action):
        action()  # Execute the action

command_handler = CommandHandler()
print("CommandHandler instance created")

# Custom OutstationApplication to log polling attempts and monitor link-layer events
class CustomOutstationApplication(opendnp3.IOutstationApplication):
    def OnStateChange(self, state):
        print(f"Outstation state changed: {state}")

    def OnReceiveIIN(self, iin):
        print(f"Polling attempt received with IIN: {iin}")

    def OnStateChange(self, value):
        print(f"Link state changed: {value}")
        if value == opendnp3.LinkStatus.UNRESET:
            self.HandleResetLinkStates()
        elif value == opendnp3.LinkStatus.RESET:
            print("Link state is now RESET")

    def OnKeepAliveInitiated(self):
        print("Keep alive initiated")

    def OnKeepAliveFailure(self):
        print("Keep alive failure")

    def OnKeepAliveSuccess(self):
        print("Keep alive success")

    def HandleResetLinkStates(self):
        print("Handling RESET_LINK_STATES")
        # Add custom logic here to handle the reset, such as resetting internal states or counters
        self.ResetInternalStates()
        # No explicit transition to RESET state is needed; the DNP3 stack will handle it.

    def ResetInternalStates(self):
        print("Resetting internal states")
        # Implement your internal state reset logic here
        self.counter = 0  # Example counter reset
        self.temp_data_buffer = []  # Example buffer clear
        # Add more reset logic as needed


outstation_application = CustomOutstationApplication()

# Configure the outstation stack
database_sizes = opendnp3.DatabaseSizes()
database_sizes.numAnalog = 7  # 7 analog values

outstation_config = asiodnp3.OutstationStackConfig(database_sizes)
outstation_config.link.LocalAddr = 1
outstation_config.link.RemoteAddr = 100

# Enable unsolicited responses
outstation_config.outstation.params.allowUnsolicited = True

# Create the outstation
print("Creating outstation")
outstation = channel.AddOutstation(
    "outstation",
    command_handler,
    outstation_application,
    outstation_config
)
print("Outstation created")

# Initialize the database with 7 analog values and set specific values
def initialize_database(outstation):
    builder = asiodnp3.UpdateBuilder()
    analog_values = {
        0: 1,  # ATLAS_AGC_STATUS_CMOD.instMag - RTAC Analog Input
        1: 2,  # ATLAS_SETPOINT_ECHO.instMag - RTAC Analog Input
        2: 3,  # ATLAS_NET_MW.instMag - RTAC Analog Input
        3: 4,  # ATLAS_LOAD.instMag - RTAC Analog Input
        4: 5,  # ATLAS_SETPOINT_INSTRUCTION - RTAC Analog Output
        5: 6,  # Atlas_Client_DNP.ATLAS_SETPOINT_INSTRUCTION.status - RTAC Analog Output
        6: 7   # Atlas_Client_DNP.ATLAS_SETPOINT_INSTRUCTION.oper - RTAC Analog Output
    }
    for i, value in analog_values.items():
        analog = opendnp3.Analog(value, opendnp3.Flags(opendnp3.AnalogQuality.ONLINE), opendnp3.DNPTime(0))
        builder.Update(analog, i)
    outstation.Apply(builder.Build())

initialize_database(outstation)

# Enable the outstation
print("Enabling outstation")
outstation.Enable()
print("Outstation enabled")

# Run the event loop
print("Press enter to exit")
input()

# Clean up and shutdown
manager.Shutdown()
