import datetime
from pprint import pprint

from bitmovin import Bitmovin, Encoding, H264CodecConfiguration, \
    AACCodecConfiguration, H264Profile, StreamInput, SelectionMode, Stream, EncodingOutput, ACLEntry, ACLPermission, \
    FMP4Muxing, MuxingStream, CloudRegion, DashManifest, FMP4Representation, FMP4RepresentationType, Period, \
    VideoAdaptationSet, AudioAdaptationSet, S3Output, TSMuxing, HlsManifest, AudioMedia, VariantStream, S3Input
from bitmovin.errors import BitmovinError

API_KEY = 'INSERT_API_KEY'

S3_INPUT_ACCESSKEY = '<INSERT_YOUR_ACCESS_KEY>'
S3_INPUT_SECRETKEY = '<INSERT_YOUR_SECRET_KEY>'
S3_INPUT_BUCKETNAME = '<INSERT_YOUR_BUCKET_NAME>'
S3_INPUT_PATH = '<INSERT_YOUR_INPUT_PATH>'

S3_OUTPUT_ACCESSKEY = '<INSERT_YOUR_ACCESS_KEY>'
S3_OUTPUT_SECRETKEY = '<INSERT_YOUR_SECRET_KEY>'
S3_OUTPUT_BUCKETNAME = '<INSERT_YOUR_BUCKET_NAME>'

date_component = str(datetime.datetime.now()).replace(' ', '_').replace(':', '-').split('.')[0].replace('_', '__')
OUTPUT_BASE_PATH = 'your/output/base/path/{}/'.format(date_component)

MEDIAN_BITRATE = 500000
MAX_COMPLEXITY_FACTOR = 1.5
MIN_COMPLEXITY_FACTOR = 0.5

# Please set here the encoding profiles. You can modify height, bitrate and fps.
encoding_profiles = [dict(height=180, bitrate=150, fps=None),
                     dict(height=180, bitrate=200, fps=None),
                     dict(height=180, bitrate=300, fps=None),
                     dict(height=270, bitrate=500, fps=None),
                     dict(height=360, bitrate=800, fps=None),
                     dict(height=360, bitrate=1000, fps=None),
                     dict(height=480, bitrate=1500, fps=None),
                     dict(height=720, bitrate=3000, fps=None),
                     dict(height=720, bitrate=4000, fps=None),
                     dict(height=1080, bitrate=6000, fps=None),
                     dict(height=1080, bitrate=7000, fps=None),
                     dict(height=1080, bitrate=10000, fps=None),
                     ]


def main():
    bitmovin = Bitmovin(api_key=API_KEY)

    # Create an S3 input. This resource is then used as base bucket for the input file.
    s3_input = S3Input(access_key=S3_INPUT_ACCESSKEY,
                       secret_key=S3_INPUT_SECRETKEY,
                       bucket_name=S3_INPUT_BUCKETNAME,
                       name='S3 Input')
    s3_input = bitmovin.inputs.S3.create(s3_input).resource

    # Create an S3 Output. This will be used as target bucket for the muxings, sprites and manifests
    s3_output = S3Output(access_key=S3_OUTPUT_ACCESSKEY,
                         secret_key=S3_OUTPUT_SECRETKEY,
                         bucket_name=S3_OUTPUT_BUCKETNAME,
                         name='S3 Output')
    s3_output = bitmovin.outputs.S3.create(s3_output).resource

    video_input_stream = StreamInput(input_id=s3_input.id,
                                     input_path=S3_INPUT_PATH,
                                     selection_mode=SelectionMode.AUTO)
    audio_input_stream = StreamInput(input_id=s3_input.id,
                                     input_path=S3_INPUT_PATH,
                                     selection_mode=SelectionMode.AUTO)

    acl_entry = ACLEntry(permission=ACLPermission.PUBLIC_READ)

    encoding_analysis = Encoding(name='Per title encoding analysis',
                                 cloud_region=CloudRegion.AWS_EU_WEST_1)
    encoding_analysis = bitmovin.encodings.Encoding.create(encoding_analysis).resource

    # Do analysis encoding to get the complexity factor
    encoding_analysis = bitmovin.encodings.Encoding.create(encoding_analysis).resource
    encoding_analysis_config = H264CodecConfiguration(
        name='H264 Per Title Analysis Configuration',
        bitrate=None,
        crf=23.0,
        height=360,
        rate=None,
        profile=H264Profile.MAIN)
    encoding_analysis_config = bitmovin.codecConfigurations.H264.create(encoding_analysis_config).resource

    encoding_analysis_stream = Stream(codec_configuration_id=encoding_analysis_config.id,
                                      input_streams=[video_input_stream],
                                      name='Per Title Analysis Stream')
    encoding_analysis_stream = bitmovin.encodings.Stream.create(object_=encoding_analysis_stream,
                                                                encoding_id=encoding_analysis.id).resource

    encoding_analysis_output = EncodingOutput(output_id=s3_output.id,
                                              output_path=OUTPUT_BASE_PATH + 'video/quality_analysis/',
                                              acl=[acl_entry])

    encoding_analysis_muxing_stream = MuxingStream(encoding_analysis_stream.id)
    encoding_analysis_muxing = FMP4Muxing(segment_length=4,
                                          segment_naming='seg_%number%.m4s',
                                          init_segment_name='init.mp4',
                                          streams=[encoding_analysis_muxing_stream],
                                          outputs=[encoding_analysis_output],
                                          name='Per Title Analysis Muxing')
    encoding_analysis_muxing = bitmovin.encodings.Muxing.FMP4.create(object_=encoding_analysis_muxing,
                                                                     encoding_id=encoding_analysis.id).resource

    bitmovin.encodings.Encoding.start(encoding_id=encoding_analysis.id)

    try:
        bitmovin.encodings.Encoding.wait_until_finished(encoding_id=encoding_analysis.id, check_interval=5)
    except BitmovinError as bitmovin_error:
        print('Exception occurred while waiting for encoding to finish: {}'.format(bitmovin_error))
        exit(-1)

    encoding_analysis_muxing = bitmovin.encodings.Muxing.FMP4.retrieve(encoding_id=encoding_analysis.id,
                                                                       muxing_id=encoding_analysis_muxing.id).resource

    # Calculate and saturate the complexity factor
    complexity_factor = encoding_analysis_muxing.avgBitrate / MEDIAN_BITRATE

    if complexity_factor > MAX_COMPLEXITY_FACTOR:
        complexity_factor = MAX_COMPLEXITY_FACTOR
    elif complexity_factor < MIN_COMPLEXITY_FACTOR:
        complexity_factor = MIN_COMPLEXITY_FACTOR

    print('Got complexity factor of: {:0.2f}'.format(complexity_factor))

    print('Updating encoding profile from:')
    pprint(encoding_profiles)
    print('To')
    # Multiply every bitrate with the complexity factor
    for profile in encoding_profiles:
        profile['bitrate'] = int(profile['bitrate'] * complexity_factor)
    pprint(encoding_profiles)

    # Create an Encoding. This will run in AWS_AP_SOUTHEAST_1. This is the base entity used to configure the encoding.
    encoding = Encoding(name='Per title encoding',
                        cloud_region=CloudRegion.AWS_EU_WEST_1)

    encoding = bitmovin.encodings.Encoding.create(encoding).resource

    encoding_configs = []

    # Iterate over all encoding profiles and create the H264 configuration with the defined height and bitrate.
    for encoding_profile in encoding_profiles:
        encoding_config = dict(profile=encoding_profile)
        codec = H264CodecConfiguration(
            name='H264 Codec {}p {}k Configuration'.format(encoding_profile.get('height'),
                                                           encoding_profile.get('bitrate')),
            bitrate=encoding_profile.get('bitrate') * 1000,
            height=encoding_profile.get('height'),
            rate=encoding_profile.get('fps'),
            profile=H264Profile.HIGH)
        encoding_config['codec'] = bitmovin.codecConfigurations.H264.create(codec).resource
        encoding_configs.append(encoding_config)

    # Also the AAC configuration has to be created, which will be later on used to create the streams.
    audio_codec_configuration = AACCodecConfiguration(name='AAC Codec Configuration',
                                                      bitrate=128000,
                                                      rate=48000)
    audio_codec_configuration = bitmovin.codecConfigurations.AAC.create(audio_codec_configuration).resource

    # With the configurations and the input file streams are now created and muxed later on.
    for encoding_config in encoding_configs:
        encoding_profile = encoding_config.get('profile')
        video_stream = Stream(codec_configuration_id=encoding_config.get('codec').id,
                              input_streams=[video_input_stream],
                              name='Stream {}p_{}k'.format(encoding_profile.get('height'),
                                                           encoding_profile.get('bitrate')))
        encoding_config['stream'] = bitmovin.encodings.Stream.create(object_=video_stream,
                                                                     encoding_id=encoding.id).resource

    audio_stream = Stream(codec_configuration_id=audio_codec_configuration.id,
                          input_streams=[audio_input_stream], name='Audio Stream')
    audio_stream = bitmovin.encodings.Stream.create(object_=audio_stream,
                                                    encoding_id=encoding.id).resource

    # Create FMP4 muxings which are later used for the DASH manifest. The current settings will set a segment length
    # of 4 seconds.
    for encoding_config in encoding_configs:
        encoding_profile = encoding_config.get('profile')
        video_muxing_stream = MuxingStream(encoding_config.get('stream').id)
        video_muxing_output = EncodingOutput(output_id=s3_output.id,
                                             output_path=OUTPUT_BASE_PATH + 'video/dash/{}p_{}k/'.format(
                                                 encoding_profile.get('height'),
                                                 encoding_profile.get('bitrate')),
                                             acl=[acl_entry])
        video_muxing = FMP4Muxing(segment_length=4,
                                  segment_naming='seg_%number%.m4s',
                                  init_segment_name='init.mp4',
                                  streams=[video_muxing_stream],
                                  outputs=[video_muxing_output],
                                  name='FMP4 Muxing {}p_{}k'.format(encoding_profile.get('height'),
                                                                    encoding_profile.get('bitrate')))
        encoding_config['fmp4_muxing'] = bitmovin.encodings.Muxing.FMP4.create(object_=video_muxing,
                                                                               encoding_id=encoding.id).resource

    audio_muxing_stream = MuxingStream(audio_stream.id)
    audio_muxing_output = EncodingOutput(output_id=s3_output.id,
                                         output_path=OUTPUT_BASE_PATH + 'audio_dash/',
                                         acl=[acl_entry])
    audio_fmp4_muxing = FMP4Muxing(segment_length=4,
                                   segment_naming='seg_%number%.m4s',
                                   init_segment_name='init.mp4',
                                   streams=[audio_muxing_stream],
                                   outputs=[audio_muxing_output],
                                   name='Audio FMP4 Muxing')
    audio_fmp4_muxing = bitmovin.encodings.Muxing.FMP4.create(object_=audio_fmp4_muxing,
                                                              encoding_id=encoding.id).resource

    # Create TS muxings which are later used for the DASH manifest. The current settings will set a segment length
    # of 4 seconds.
    for encoding_config in encoding_configs:
        encoding_profile = encoding_config.get('profile')
        video_muxing_stream = MuxingStream(encoding_config.get('stream').id)
        video_muxing_output = EncodingOutput(output_id=s3_output.id,
                                             output_path=OUTPUT_BASE_PATH + 'video/hls/{}p_{}k/'.format(
                                                 encoding_profile.get('height'),
                                                 encoding_profile.get('bitrate')),
                                             acl=[acl_entry])
        video_muxing = TSMuxing(segment_length=4,
                                segment_naming='seg_%number%.ts',
                                streams=[video_muxing_stream],
                                outputs=[video_muxing_output],
                                name='TS Muxing {}p_{}k'.format(encoding_profile.get('height'),
                                                                encoding_profile.get('bitrate')))
        encoding_config['ts_muxing'] = bitmovin.encodings.Muxing.TS.create(object_=video_muxing,
                                                                           encoding_id=encoding.id).resource

    audio_muxing_stream = MuxingStream(audio_stream.id)
    audio_muxing_output = EncodingOutput(output_id=s3_output.id,
                                         output_path=OUTPUT_BASE_PATH + 'audio_hls/',
                                         acl=[acl_entry])
    audio_ts_muxing = TSMuxing(segment_length=4,
                               segment_naming='seg_%number%.ts',
                               streams=[audio_muxing_stream],
                               outputs=[audio_muxing_output],
                               name='Audio TS Muxing')
    audio_ts_muxing = bitmovin.encodings.Muxing.TS.create(object_=audio_ts_muxing,
                                                          encoding_id=encoding.id).resource

    bitmovin.encodings.Encoding.start(encoding_id=encoding.id)

    try:
        bitmovin.encodings.Encoding.wait_until_finished(encoding_id=encoding.id, check_interval=5)
    except BitmovinError as bitmovin_error:
        print('Exception occurred while waiting for encoding to finish: {}'.format(bitmovin_error))
        exit(-1)

    # Specify the output for manifest which will be in the OUTPUT_BASE_PATH.
    manifest_output = EncodingOutput(output_id=s3_output.id,
                                     output_path=OUTPUT_BASE_PATH,
                                     acl=[acl_entry])
    # Create a DASH manifest and add one period with an adapation set for audio and video
    dash_manifest = DashManifest(manifest_name='stream.mpd',
                                 outputs=[manifest_output],
                                 name='DASH Manifest')
    dash_manifest = bitmovin.manifests.DASH.create(dash_manifest).resource
    period = Period()
    period = bitmovin.manifests.DASH.add_period(object_=period, manifest_id=dash_manifest.id).resource
    video_adaptation_set = VideoAdaptationSet()
    video_adaptation_set = bitmovin.manifests.DASH.add_video_adaptation_set(object_=video_adaptation_set,
                                                                            manifest_id=dash_manifest.id,
                                                                            period_id=period.id).resource

    audio_adaptation_set = AudioAdaptationSet(lang='en')
    audio_adaptation_set = bitmovin.manifests.DASH.add_audio_adaptation_set(object_=audio_adaptation_set,
                                                                            manifest_id=dash_manifest.id,
                                                                            period_id=period.id).resource

    # Add all representation to the video adaption set
    for encoding_config in encoding_configs:
        encoding_profile = encoding_config.get('profile')
        muxing = encoding_config.get('fmp4_muxing')
        fmp4_representation_1080p = FMP4Representation(FMP4RepresentationType.TEMPLATE,
                                                       encoding_id=encoding.id,
                                                       muxing_id=muxing.id,
                                                       segment_path='video/dash/{}p_{}k/'.format(
                                                           encoding_profile.get('height'),
                                                           encoding_profile.get('bitrate')))
        encoding_config['dash'] = bitmovin.manifests.DASH.add_fmp4_representation(object_=fmp4_representation_1080p,
                                                                                  manifest_id=dash_manifest.id,
                                                                                  period_id=period.id,
                                                                                  adaptationset_id=video_adaptation_set.id
                                                                                  ).resource

    fmp4_representation_audio = FMP4Representation(FMP4RepresentationType.TEMPLATE,
                                                   encoding_id=encoding.id,
                                                   muxing_id=audio_fmp4_muxing.id,
                                                   segment_path='audio_dash/')
    bitmovin.manifests.DASH.add_fmp4_representation(object_=fmp4_representation_audio,
                                                    manifest_id=dash_manifest.id,
                                                    period_id=period.id,
                                                    adaptationset_id=audio_adaptation_set.id)

    bitmovin.manifests.DASH.start(manifest_id=dash_manifest.id)

    # Create a HLS manifest and add one period with an adapation set for audio and video
    hls_manifest = HlsManifest(manifest_name='stream.m3u8',
                               outputs=[manifest_output],
                               name='HLS Manifest')
    hls_manifest = bitmovin.manifests.HLS.create(hls_manifest).resource

    audio_media = AudioMedia(name='HLS Audio Media', group_id='audio',
                             segment_path='audio_hls/', encoding_id=encoding.id,
                             stream_id=audio_stream.id, muxing_id=audio_ts_muxing.id, language='en', uri='audio.m3u8')
    audio_media = bitmovin.manifests.HLS.AudioMedia.create(manifest_id=hls_manifest.id, object_=audio_media).resource

    # Add all representation to the video adaption set
    for encoding_config in encoding_configs:
        encoding_profile = encoding_config.get('profile')
        stream = encoding_config.get('stream')
        muxing = encoding_config.get('ts_muxing')
        variant_stream = VariantStream(audio='audio',
                                       closed_captions='NONE',
                                       segment_path='video/hls/{}p_{}k/'.format(
                                           encoding_profile.get('height'),
                                           encoding_profile.get('bitrate')),
                                       uri='video_{}p_{}k.m3u8'.format(
                                           encoding_profile.get('height'),
                                           encoding_profile.get('bitrate')),
                                       encoding_id=encoding.id,
                                       stream_id=stream.id,
                                       muxing_id=muxing.id)
        variant_stream = bitmovin.manifests.HLS.VariantStream.create(manifest_id=hls_manifest.id,
                                                                     object_=variant_stream).resource

    bitmovin.manifests.HLS.start(manifest_id=hls_manifest.id)

    try:
        bitmovin.manifests.DASH.wait_until_finished(manifest_id=dash_manifest.id, check_interval=1)
    except BitmovinError as bitmovin_error:
        print('Exception occurred while waiting for manifest creation to finish: {}'.format(bitmovin_error))
        exit(-1)

    try:
        bitmovin.manifests.HLS.wait_until_finished(manifest_id=hls_manifest.id, check_interval=1)
    except BitmovinError as bitmovin_error:
        print('Exception occurred while waiting for manifest creation to finish: {}'.format(bitmovin_error))
        exit(-1)


if __name__ == '__main__':
    main()
