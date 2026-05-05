import numpy
import numpy as np
import scipy.signal

# for testing
import matplotlib.pyplot as pp

from typing import Tuple
import nidaqmx
from nidaqmx.stream_writers import CounterWriter
from nidaqmx.constants import AcquisitionType, Level



def set_DC_Voltage(voltage = 0.0):
    with nidaqmx.Task() as task:
        task.ao_channels.add_ao_voltage_chan(physical_channel='Dev1/ao0')
        task.write(voltage)


def generate_sine_wave(
    frequency: float,
    amplitude: float,
    sampling_rate: float,
    number_of_samples: int,
    phase_in: float = 0.0,
) -> Tuple[numpy.typing.NDArray[numpy.double], float]:
    """Generates a sine wave with a specified phase.

    Args:
        frequency: Specifies the frequency of the sine wave.
        amplitude: Specifies the amplitude of the sine wave.
        sampling_rate: Specifies the sampling rate of the sine wave.
        number_of_samples: Specifies the number of samples to generate.
        phase_in: Specifies the phase of the sine wave in radians.

    Returns:
        Indicates a tuple containing the generated data and the phase
        of the sine wave after generation.
    """
    duration_time = number_of_samples / sampling_rate
    duration_radians = duration_time * 2 * np.pi
    phase_out = (phase_in + duration_radians) % (2 * np.pi)
    t = np.linspace(phase_in, phase_in + duration_radians, number_of_samples, endpoint=False)

    return (amplitude * np.sin(frequency * t), phase_out)

def generate_ramp_wave(
    cycle_frequency: float,
    amplitude: float,
    offset: float,
    number_of_samples: int,
    ramp_width: float = 1.0):

    sig_f = 2 * np.pi

    t = np.linspace(
        start = 0,
        stop = 1,
        num = number_of_samples,
        endpoint=False)

    sig = (amplitude * (scipy.signal.sawtooth(t * sig_f, ramp_width)) + offset)
    # print(t)

    do_plot = False
    if do_plot:
        fig, ax = pp.subplots(1,1)
        ax.plot(t*sig_f, sig)
        pp.draw()
        pp.waitforbuttonpress()
    
    print(f'cyc_freq = {cycle_frequency},\namplitude = {amplitude}\nsample_nr = {number_of_samples}')
    
    return sig

# print( generate_ramp_wave(frequency=1, amplitude=1, offset=0.0, sampling_rate=1000, number_of_samples=1000, phase_in=0.0))
# pp.plot(generate_ramp_wave(frequency=1, amplitude=1, offset=0.0, sampling_rate=1800, number_of_samples=1000, phase_in=0.0)[0])
# pp.show()

# The short pulse train generation for a triger for each line does not work like that.
# We can send a long duty cycle during which time the camera just captures all frames and we collect what we get.
# Because we do not have any easy access to synchronize the USB connection.
# For that we can use the counter output again.
# The camera transfers less than 4000 lines per seconds.
# Assuming our ramp time can be adjusted we can make it large enough that we get all frames.
# Assuming the camera could transfer 4000 lps and we collect 4000 lines we would have a frame rate of 1 fps.
# So could make our ramp signal 1 Hz and the duty cycle could be somewhat shorter still providing sufficient time
# to collect all camera lines assuming it is anyway slower.
# To use somewhat more relevant numbers, the line samples are 2048 so we get close to 2 fps.

def update_ramp_task(
        # currently this function is not in use.
        sampling_rate = 1900,
        number_of_samples = 1000,
        frequency = 1.0,
        amplitude = 1.0,
        offset = 0.0,
        phase_in = 0.0):
    do_not_start = False
    run_ramp_task(
        sampling_rate = 1900,
        number_of_samples = 1000,
        frequency = 1.0,
        amplitude = 1.0,
        offset = 0.0,
        phase_in = 0.0,
        do_start = do_not_start)

def run_daq_tasks(
        # setting sampling_rate = 1000 and test freqency
        # need to monitor the ramp on the soci now.
        sampling_rate = 2048,
        number_of_samples = 1000,
        frequency = 1.0,
        amplitude = 1.0,
        offset = 0.0,
        phase_in = 0.0,
        cam_duty = 0.95,
        do_start = True):
    
    """
    Continuously generates a ramp signal.
    frequency = 1.0 ... is the number of cycles per number of samples
    """

    task = nidaqmx.Task(new_task_name='Ramp-task')
    print(task)

    # with nidaqmx.Task() as task:
    task.ao_channels.add_ao_voltage_chan("Dev1/ao0")
    # TODO: hard coded parameters for testing
    gen_rate = 2700
    rate = gen_rate/2.048
    samps_per_chan = 2048
    cam_rate = gen_rate
    print(f'rate: {rate}, samps: {samps_per_chan}, cam_rate: {cam_rate}')
    
    task.timing.cfg_samp_clk_timing(
        rate = rate,
        sample_mode=AcquisitionType.CONTINUOUS,
        samps_per_chan=samps_per_chan)

    actual_sampling_rate = task.timing.samp_clk_rate
    print(f"Actual sampling rate: {actual_sampling_rate:g} S/s")

    #####
    # Cam trigger
    ptask = nidaqmx.Task(new_task_name = 'Test_Cam_Trig_v0')
    ch = ptask.co_channels.add_co_pulse_chan_time(counter="Dev1/ctr0")
    # ch = ptask.co_channels.add_co_pulse_chan_freq(
        # "Dev1/ctr0",
        # idle_state=Level.LOW,
        # initial_delay=0.0,
        # freq=1.5,
        # duty_cycle= 0.99#cam_duty # 500000E-6
    # )

    ptask.timing.cfg_implicit_timing(sample_mode=AcquisitionType.CONTINUOUS)
    ch.co_pulse_term = "/Dev1/PFI12" # may not be required as this is the default
    
    # I guess for the PFI we can not use this function as it does not prepare
    # the buffer.
    # We get then a buffer error.
    # ptask.timing.cfg_samp_clk_timing(
        # sampling_rate,
        # sample_mode = AcquisitionType.CONTINUOUS,
        # samps_per_chan = number_of_samples)

    cw = CounterWriter(ptask.out_stream, True)
    # the task seems need to have started before it can be written to.
    ptask.start()
    cw.write_one_sample_pulse_frequency(frequency=cam_rate, duty_cycle=0.5, timeout=5000)

    ramp_sig = generate_ramp_wave(
        cycle_frequency=None,
        amplitude=amplitude,
        offset=offset,
        # The example copy did also change the numerical rate which is changing the period.
        number_of_samples=1000, #number_of_samples,
        ramp_width=1.0
    )

    task.write(ramp_sig) #todo: can we update while the task is running?


    if do_start:
        task.start()
        # ptask.start()

        
    # input("Generating voltage continuously. Press Enter to stop.\n")
    return {'ramp_task': task, 'trig_task': ptask}

        # task.stop()

# run_sinusoidal_signal()

