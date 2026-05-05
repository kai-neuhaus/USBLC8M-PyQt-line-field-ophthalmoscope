'''
From
https://nspyre.readthedocs.io/en/latest/guides/ni-daqmx.html
'''

import nidaqmx
from nidaqmx.constants import (AcquisitionType, CountDirection, Edge,
    READ_ALL_AVAILABLE, TaskMode, TriggerType)
from nidaqmx.stream_readers import CounterReader
import numpy


# Let's load up the NI-DAQmx system that is visible in the
# Measurement & Automation Explorer (MAX) software of NI-DAQmx for
# the local machine.
system = nidaqmx.system.System.local()
print(system.devices.device_names)
# We know on our current system that our DAQ is named 'DAQ1'
DAQ_device = system.devices['Dev1']
# create a list of all the counters available on 'DAQ1'
counter_names = [ci.name for ci in DAQ_device.ci_physical_chans]
print(counter_names)

# note that using the counter output channels instead of the inputs
# includes the '[device]/freqout' output, which is not a counter
print([co.name for co in DAQ_device.co_physical_chans])

# My additions
print([ai.name for ai in DAQ_device.ai_physical_chans])

print([ao.name for ao in  DAQ_device.ao_physical_chans])


# I copy this now from the link above step-by-step
# As far as I see this is what we might be using.
# It prepares two channels and one is the trigger channelw ith

nidaqmx.Task() as read_task:
 xpass
#nidaqmx.Task() as read_task:


#nidaqmx.Task() as samp_clk_task:


#     # So if I see this right we detect a trigger on digital port0
#     # The port2 does not support buffered operation.
#     samp_clk_task.di_channels.add_di_chan('Dev1/port0')

#     sampling_rate = 100
#     samp_clk_task.timing.cfg_samp_clk_timing(
#         sampling_rate,
#         sample_mode=AcquisitionType.CONTINUOUS)

#     # This kind of loads the parameters into the Daq hardware.
#     # This is not strictly required but it is faster if to start it.
#     samp_clk_task.control(TaskMode.TASK_COMMIT)


#     # Counter input.
    
#     read_task.ci_channels.add_ci_count_edges_chan(
#                                 'Dev1/ctr0',
#                                 edge=Edge.RISING,
#                                 initial_count=0,
#                                 count_direction=CountDirection.COUNT_UP)
    
#     # Is this just configuring the connector for ctr0?
#     # The example description sounds like that.
#     # The leading '/' is required in this case.
#     read_task.ci_channels.all.ci_count_edges_term = '/Dev1/PFI5'



#     # Configure the timing parameters
#     read_task.timing.cfg_samp_clk_timing(
#         sampling_rate,
#         source='/Dev1/di/SampleClock',
#         active_edge=Edge.RISING,
#         sample_mode=AcquisitionType.CONTINUOUS)


#     read_task.in_stream.input_buf_size = 12000

#     # triggers can be configured to occur on a digital edge, an analog edge, or when an analog signal enters or leaves a window. (Other triggers include: arm start trigger [for counters only], pause trigger, and handshake trigger.)

#     # This should make a trigger such that the reader is starting at some defined trigger signal
#     read_task.triggers.arm_start_trigger.trig_type = TriggerType.DIGITAL_EDGE
    
#     read_task.triggers.arm_start_trigger.dig_edge_edge = Edge.RISING
#     read_task.triggers.arm_start_trigger.dig_edge_src = '/Dev1/di/SampleClock'

#     # Use buffered reading
#     reader = CounterReader(read_task.in_stream)

#     # Start both tasks
#     # Note that the sequential call here or the order does not matter.
#     # The trigger will determine when the reader starts.
#     # Even if we start samp_clk_task after it would work.
#     samp_clk_task.start()
#     read_task.start()

#     data_array = numpy.zeros(12000, dtype=numpy.uint32)

#     reader.read_many_sample_uint32(
#         data_array,
#         number_of_samples_per_channel=READ_ALL_AVAILABLE)

#     print(data_array)
#     # stopping and closing will be pefromed automatically using with
#     # here as an example we use them explicitly also to stop and restart
#     read_task.stop()
#     read_task.start()
#     print(data_array)
#     read_task.close()

    
