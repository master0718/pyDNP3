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
        if isinstance(command, opendnp3.AnalogOutputInt16) and index == 1:
            self.selected_index = index
            return opendnp3.CommandStatus.SUCCESS
        return opendnp3.CommandStatus.NOT_SUPPORTED

    def Operate(self, command, index, op_type):
        print(f"Operate command: {command}, index: {index}, type: {op_type}")
        if isinstance(command, opendnp3.AnalogOutputInt16) and self.selected_index == index:
            value = command.value
            print(f"Analog value received for index {index}: {value}")

            # Update the outstation database with the received value
            builder = asiodnp3.UpdateBuilder()
            analog = opendnp3.Analog(value, opendnp3.Flags(opendnp3.AnalogQuality.ONLINE), opendnp3.DNPTime(0))
            builder.Update(analog, 1)  # Update Atlas_Client_DNP.ATLAS_SETPOINT_INSTRUCTION.status
            outstation.Apply(builder.Build())

            # Echo the value to Atlas_Client_DNP.ATLAS_SETPOINT_ECHO
            builder.Update(analog, 2)  # Update Atlas_Client_DNP.ATLAS_SETPOINT_ECHO
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

    def OnKeepAliveInitiated(self):
        print("Keep alive initiated")

    def OnKeepAliveFailure(self):
        print("Keep alive failure")

    def OnKeepAliveSuccess(self):
        print("Keep alive success")

    def HandleResetLinkStates(self):
        print("Handling RESET_LINK_STATES")
        self.ResetInternalStates()

    def ResetInternalStates(self):
        print("Resetting internal states")
        self.counter = 0
        self.temp_data_buffer = []

outstation_application = CustomOutstationApplication()

# Configure the outstation stack
database_sizes = opendnp3.DatabaseSizes()
database_sizes.numAnalog = 3  # Adjust as needed

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

# Initialize the database with initial analog values
def initialize_database(outstation):
    builder = asiodnp3.UpdateBuilder()
    analog_values = {
        0: 1,  # ATLAS_AGC_STATUS_CMOD.instMag - RTAC Analog Input
        1: 0,  # ATLAS_SETPOINT_ECHO.instMag - RTAC Analog Input (initially 0)
        2: 0   # ATLAS_SETPOINT_INSTRUCTION.status - RTAC Analog Output (initially 0)
    }
    for index, value in analog_values.items():
        analog = opendnp3.Analog(value, opendnp3.Flags(opendnp3.AnalogQuality.ONLINE), opendnp3.DNPTime(0))
        builder.Update(analog, index)
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
